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
STORE_SPRAVZHNII = (store.get_user, store.purchases_of)   # для розділу 5
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

print("5. «Видати вручну» без рядка покупки (оплата БЕЗ КОДУ)")
# Підставна таблиця purchases за справжніми функціями store.py: fake_q розуміє
# рівно ті запити, які шлють add_purchase, ensure_purchase, mark_paid,
# mark_delivered, get_purchase, purchases_of, get_user. Решта мовчить.
store.get_user, store.purchases_of = STORE_SPRAVZHNII
BAZA = {"purchases": [], "users": {}}


def fake_q5(sql, args=(), fetch=None):
    s = " ".join(sql.split())
    ps = BAZA["purchases"]
    if s.startswith("insert into purchases"):
        uid, product, tier, code, uah = args[:5]
        tag = args[5] if "coalesce" in s else None
        tag = tag or (BAZA["users"].get(args[-2]) or {}).get("source_tag")
        was = [p for p in ps if p["order_code"] == code]
        if was:
            if "do nothing" in s:
                return None
            was[0]["amount_uah"] = uah
            return was[0]
        row = {"id": len(ps) + 1, "user_id": uid, "product": product, "tier": tier,
               "order_code": code, "amount_uah": uah, "status": "new", "source_tag": tag,
               "slots_total": args[-1], "slots_used": 0, "created_at": T,
               "paid_at": None, "delivered_at": None}
        ps.append(row)
        return row
    if s.startswith("update purchases set status = 'paid'"):
        uah, code = args
        for p in ps:
            if p["order_code"] == code and p["status"] == "new":
                p.update(status="paid", paid_at=T, amount_uah=uah if uah is not None else p["amount_uah"])
                return p
        return None
    if s.startswith("update purchases set status = 'delivered'"):
        for p in ps:
            if p["order_code"] == args[0]:
                p.update(status="delivered", delivered_at=T)
                return p
        return None
    if s.startswith("select * from purchases where order_code"):
        return next((p for p in ps if p["order_code"] == args[0]), None)
    if s.startswith("select * from purchases where user_id"):
        return [p for p in ps if p["user_id"] == args[0]
                and ("status in" not in s or p["status"] in ("paid", "delivered"))]
    if s.startswith("select * from users where user_id"):
        return BAZA["users"].get(args[0])
    return None if fetch != "all" else []


store.q = fake_q5
bot.COURSE_SECTIONS["k1"] = bot.parse_course("Урок 1 > video:V1 | Урок 2 > document:D2")
for uid in (801, 802, 803):
    BAZA["users"][uid] = dict(USERS[777], user_id=uid, source_tag="inst", got_magnet_at=None)


def ryadky(uid):
    return [p for p in BAZA["purchases"] if p["user_id"] == uid]


def moi_bachyt(uid, ckey="k1"):
    VYKLYKY.clear()
    cb("moi", uid=uid)
    kb = json.dumps([p.get("reply_markup") for m, p in VYKLYKY if p.get("chat_id") == uid], ensure_ascii=False)
    return ('"les:' + ckey + ':0"') in kb


def kabinet_maie(code, s=5.0):
    kin = time.time() + s
    while time.time() < kin:
        for g in list(Kab.got):
            for p in (g["body"] or {}).get("purchases") or []:
                if p.get("order_code") == code and p.get("status") == "delivered":
                    return p
        time.sleep(0.02)
    return None


KOD_A = bot.order_code(801, "k1")
ok("до видачі рядка нема і /moi порожній", ryadky(801) == [] and not moi_bachyt(801))
Kab.got.clear()
VYKLYKY.clear()
r = cb("give:801:k1", uid=1)
ok("адмін бачить «Видано»", r.status_code == 200 and any(
   m == "sendMessage" and p.get("chat_id") == 1 and p.get("text") == "Видано" for m, p in VYKLYKY))
ok("уроки пішли людині", "sendMessage" in tg_do(801) or "sendVideo" in tg_do(801), str(tg_do(801)))
ra = ryadky(801)
ok("рівно один рядок", len(ra) == 1, str(len(ra)))
a = ra[0] if ra else {}
ok("код за правилом order_code", a.get("order_code") == KOD_A == "IR" + bot.b36(801) + "-4", str(a.get("order_code")))
ok("статус delivered, paid_at і delivered_at є", a.get("status") == "delivered"
   and a.get("paid_at") is not None and a.get("delivered_at") is not None, str(a))
ok("product/tier/сума/мітка як при виборі тарифу", a.get("product") == "course" and a.get("tier") == "k1"
   and a.get("amount_uah") == bot.PRODUCTS["k1"]["uah"] and a.get("source_tag") == "inst"
   and a.get("slots_total") == 0, str(a))
ok("/moi бачить курс", moi_bachyt(801))
pk = kabinet_maie(KOD_A)
ok("міст штовхнув покупку в кабінет", pk is not None and pk.get("tier") == "k1"
   and pk.get("user_id") == 801, str(pk))

# той самий кінцевий стан, що й після звичайної оплати з кодом. Кнопка тарифу
# курсу без COURSES_ON закрита, тож рядок кладемо тим самим викликом, що bot.py
# при виборі тарифу (add_purchase з ціною тарифу).


def vybir_taryfu(uid, key):
    store.add_purchase(uid, bot.PRODUCTS[key]["product"], tier=key,
                       order_code=bot.order_code(uid, key), amount_uah=bot.PRODUCTS[key]["uah"])


vybir_taryfu(802, "k1")
bot.handle_tx(tx(802, "k1", bot.PRODUCTS["k1"]["uah"]))
rb = ryadky(802)
POLIA = ("product", "tier", "status", "amount_uah", "source_tag", "slots_total", "slots_used")
ok("оплата з кодом дає той самий рядок", len(rb) == 1 and all(rb[0][k] == a.get(k) for k in POLIA)
   and rb[0]["paid_at"] is not None and rb[0]["delivered_at"] is not None,
   str([(k, rb[0][k] if rb else None, a.get(k)) for k in POLIA]))

print("5б. Повторне натискання: без дублікатів")
Kab.got.clear()
r = cb("give:801:k1", uid=1)
ra = ryadky(801)
ok("той самий один рядок", r.status_code == 200 and len(ra) == 1 and len(BAZA["purchases"]) == 2,
   str(len(BAZA["purchases"])))
ok("статус лишився delivered", ra and ra[0]["status"] == "delivered")
pk = kabinet_maie(KOD_A)
ok("кабінет знову отримав ту саму одну покупку", pk is not None and all(
   len([p for p in (g["body"] or {}).get("purchases") or [] if p.get("order_code") == KOD_A]) <= 1
   for g in Kab.got))

print("5в. Рядок new вже є (людина натиснула тариф): як і раніше")
vybir_taryfu(803, "k1")
KOD_C = bot.order_code(803, "k1")
ryadky(803)[0]["amount_uah"] = 555          # ensure_purchase не має чіпати наявний рядок
cb("give:803:k1", uid=1)
rc = ryadky(803)
ok("один рядок, delivered", len(rc) == 1 and rc[0]["status"] == "delivered", str(rc))
ok("наявний рядок не переписано (сума 555)", rc and rc[0]["amount_uah"] == 555)
ok("кабінет отримав", kabinet_maie(KOD_C) is not None)

print("5г. Видача не вдалась: рядка не створюємо (як і раніше)")
n0 = len(BAZA["purchases"])
VYKLYKY.clear()
cb("give:804:k2", uid=1)                    # у k2 уроків нема → deliver False
ok("рядка нема", len(BAZA["purchases"]) == n0 and ryadky(804) == [])
ok("адмін бачить «Не вдалося»", any(m == "sendMessage" and p.get("chat_id") == 1
   and str(p.get("text", "")).startswith("Не вдалося") for m, p in VYKLYKY))
store.q = store_q

srv.shutdown()
print()
print("ПАДІНЬ:", len(PADINNIA))
for x in PADINNIA:
    print("  -", x)
sys.exit(1 if PADINNIA else 0)
