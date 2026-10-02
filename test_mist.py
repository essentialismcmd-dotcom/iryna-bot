#!/usr/bin/env python3
"""
Міст баз (02.10) БЕЗ мережі, бази і телеграма: kabinet_mist.py і вставки в bot.py.

1. Без KABINET_URL і KABINET_KEY моста нема: жодного запиту, потоку, звірки.
2. Зі змінними: після магніта і оплати бот шле людину і покупки на підставний
   сервер /internal/sync з заголовком X-Internal-Key.
3. Кабінет падає (500, мовчить, повільний): видача іде, бот не чекає.
4. Звірка шле всіх пачками по 200.

Запуск:  python test_mist.py   (виходить 0, якщо все зелене)
"""

import os, sys, json, time, threading, importlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "MAGNET_URL": "MAGNIT",
                   "NOTIFY_IDS": "1", "CHANNEL_URL": "https://t.me/test_kanal"})
for k in ("DATABASE_URL", "PAY_URL", "COURSES_ON", "GUIDE_PRICE", "COURSE_PRICES", "TEST_MODE",
          "KABINET_URL", "KABINET_KEY", "KABINET_ZVIRKA_S"):
    os.environ.pop(k, None)

import requests

REAL_POST = requests.post
VYKLYKY = []      # телеграм
DO_KABINETU = []  # усі запити не в телеграм, навіть якщо міст мав би мовчати


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, headers=None):
    if "api.telegram.org" not in url:
        DO_KABINETU.append(url)
        return REAL_POST(url, json=json, headers=headers, timeout=timeout)
    method = url.rsplit("/", 1)[-1]
    VYKLYKY.append((method, json or data or {}))
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import store
import bot
import kabinet_mist

app = bot.app.test_client()
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


def cb(data, uid=777):
    return app.post("/sekret", json={"callback_query": {"id": "c", "data": data,
                    "from": {"id": uid, "first_name": "Т"}, "message": {"chat": {"id": uid}, "message_id": 5}}})


def tg_do(chat_id):
    return [m for m, p in VYKLYKY if p.get("chat_id") == chat_id]


# ---------- підставна база бота ----------

T = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
USERS = {777: {"user_id": 777, "username": "tester", "first_name": "Т", "last_name": None,
               "role": "client", "source_tag": "ig", "created_at": T, "last_seen_at": T,
               "got_magnet_at": T, "got_guide_at": None, "cabinet_msg": 55}}
PURCHASES = {777: [{"id": 1, "user_id": 777, "product": "course", "tier": "k1",
                    "order_code": bot.order_code(777, "k1"), "amount_uah": 700,
                    "status": "paid", "source_tag": "ig", "slots_total": 0, "slots_used": 0,
                    "created_at": T, "paid_at": T, "delivered_at": None}]}
store.get_user = lambda uid: USERS.get(uid)
store.purchases_of = lambda uid, only_paid=True: PURCHASES.get(uid, [])


# ---------- підставний кабінет ----------

class Kab:
    status = 200
    delay = 0.0
    got = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"null")
        Kab.got.append({"path": self.path, "key": self.headers.get("X-Internal-Key"), "body": body})
        time.sleep(Kab.delay)
        self.send_response(Kab.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]


def chekaty(n, s=5.0):
    kin = time.time() + s
    while time.time() < kin and len(Kab.got) < n:
        time.sleep(0.02)
    return len(Kab.got) >= n


def tx(uid=777, key="k1", uah=100000):
    return {"id": "tx%f" % time.time(), "amount": uah * 100, "comment": bot.order_code(uid, key),
            "description": "Т", "time": int(time.time())}


print("1. Без змінних моста нема")
ok("ON вимкнений", kabinet_mist.ON is False)
pered = threading.active_count()
cb("magnet")
bot.handle_tx(tx())
cb("guide")
ok("push_user нічого не робить", kabinet_mist.push_user(777) is None)
ok("start нічого не робить", kabinet_mist.start() is None)
ok("звірка нічого не робить", kabinet_mist.zvirka() is None)
ok("post нічого не шле", kabinet_mist.post({"users": []}) is False)
ok("жодного запиту поза телеграмом", DO_KABINETU == [], str(DO_KABINETU))
ok("нових потоків нема", threading.active_count() == pered,
   "%d → %d" % (pered, threading.active_count()))
ok("магніт видано як і раніше", "sendDocument" in tg_do(777) or "sendMessage" in tg_do(777))

# лише одна змінна: теж вимкнено
os.environ["KABINET_URL"] = "http://127.0.0.1:%d" % PORT
importlib.reload(kabinet_mist)
ok("без KABINET_KEY вимкнено", kabinet_mist.ON is False)

print("2. Зі змінними: правильне тіло і заголовок")
os.environ["KABINET_KEY"] = "test-internal-key"
importlib.reload(kabinet_mist)
kabinet_mist._sleep = lambda s: None          # без пауз між спробами
ok("ON увімкнений", kabinet_mist.ON is True)
ok("bot бачить той самий модуль", bot.kabinet_mist is kabinet_mist)
Kab.got.clear()
r = cb("magnet")
ok("відповідь бота 200", r.status_code == 200)
ok("кабінет отримав запит", chekaty(1))
g = Kab.got[0] if Kab.got else {}
ok("шлях /internal/sync", g.get("path") == "/internal/sync", str(g.get("path")))
ok("заголовок X-Internal-Key", g.get("key") == "test-internal-key")
b = g.get("body") or {}
u = (b.get("users") or [{}])[0]
p = (b.get("purchases") or [{}])[0]
ok("людина з полями", u.get("user_id") == 777 and u.get("got_magnet_at") == T.isoformat(), str(u))
ok("cabinet_msg не йде", "cabinet_msg" not in u)
ok("покупка з order_code і статусом", p.get("order_code") == bot.order_code(777, "k1")
   and p.get("status") == "paid" and p.get("tier") == "k1", str(p))
ok("id покупки не йде", "id" not in p)
ok("дати рядком з поясом", p.get("paid_at") == "2026-10-02T08:00:00+00:00")

Kab.got.clear()
bot.handle_tx(tx())
ok("після оплати теж шле", chekaty(1))

Kab.got.clear()
cb("guide")
ok("після гайда теж шле", chekaty(1))

print("3. Кабінет падає: бот не падає і не чекає")
Kab.got.clear()
Kab.status = 500
VYKLYKY.clear()
r = cb("magnet")
ok("відповідь бота 200 при 500 у кабінеті", r.status_code == 200)
ok("магніт видано", bool(tg_do(777)))
ok("три спроби", chekaty(3) and len(Kab.got) == 3, str(len(Kab.got)))
time.sleep(0.2)
ok("не більше трьох", len(Kab.got) == 3, str(len(Kab.got)))

Kab.got.clear()
Kab.status = 403
kabinet_mist._push_user_now(777)
ok("403 без повторів", len(Kab.got) == 1, str(len(Kab.got)))

Kab.status = 200
Kab.delay = 2.0
Kab.got.clear()
t0 = time.time()
bot.handle_tx(tx())
dt = time.time() - t0
ok("оплата не чекає повільний кабінет", dt < 1.0, "%.2f с" % dt)
chekaty(1)
Kab.delay = 0.0

os.environ["KABINET_URL"] = "http://127.0.0.1:1"      # порт, де нікого нема
importlib.reload(kabinet_mist)
kabinet_mist._sleep = lambda s: None
ok("кабінет лежить: post False без винятку", kabinet_mist.post({"users": []}) is False)
t0 = time.time()
r = cb("magnet")
ok("кабінет лежить: бот відповідає", r.status_code == 200 and time.time() - t0 < 1.0)


def boom(uid):
    raise RuntimeError("база впала")


store_get = store.get_user
store.get_user = boom
try:
    kabinet_mist._push_user_now(777)
    ok("помилка бази в потоці не вилітає", True)
except Exception as e:
    ok("помилка бази в потоці не вилітає", False, repr(e))
store.get_user = store_get

print("4. Звірка пачками")
os.environ["KABINET_URL"] = "http://127.0.0.1:%d" % PORT
importlib.reload(kabinet_mist)
kabinet_mist._sleep = lambda s: None
Kab.got.clear()
VSI_P = [dict(PURCHASES[777][0], id=i, user_id=1000 + i, order_code="IR%d-4" % i)
         for i in range(450)]
VSI_U = [dict(USERS[777], user_id=1000 + i) for i in range(450)]
ZAPYTY = []


def fake_q(sql, args=(), fetch=None):
    ZAPYTY.append(sql)
    return VSI_P if "from purchases" in sql.split("where")[0] else VSI_U


store_q = store.q
store.q = fake_q
n = kabinet_mist.zvirka()
store.q = store_q
ok("6 пачок прийнято (3 людей + 3 покупок)", n == 6, str(n))
rozmiry = [len(g["body"]["users"]) + len(g["body"]["purchases"]) for g in Kab.got]
ok("пачки по 200, 200, 50", sorted(rozmiry) == [50, 50, 200, 200, 200, 200], str(rozmiry))
ok("усі покупки дійшли", sum(len(g["body"]["purchases"]) for g in Kab.got) == 450)
ok("усі люди дійшли", sum(len(g["body"]["users"]) for g in Kab.got) == 450)
ok("звірка бере лише paid/delivered", "status in ('paid', 'delivered')" in ZAPYTY[0])
ok("звірка бере магніт і гайд", "got_magnet_at is not null" in ZAPYTY[1]
   and "got_guide_at is not null" in ZAPYTY[1])

# звірка не йде двічі паралельно
kabinet_mist._zvirka_lock.acquire()
ok("друга звірка в той самий час пропускається", kabinet_mist.zvirka() is None)
kabinet_mist._zvirka_lock.release()

srv.shutdown()
print()
print("ПАДІНЬ:", len(PADINNIA))
for x in PADINNIA:
    print("  -", x)
sys.exit(1 if PADINNIA else 0)
