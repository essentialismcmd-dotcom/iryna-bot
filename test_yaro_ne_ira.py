#!/usr/bin/env python3
"""
Акаунти Yaro не шлють службових сповіщень Ірі (14.10) БЕЗ мережі і бази. Тричі за 14.10 тести з акаунта Yaro
(«/podarunok …», «C:/Program Files/Git/do…», «C:/Program Files/Git/nova» плюс ЗАЯВКА від кліку «Курс ретуші»)
дійшли Ірі як «Повідомлення в боті від YR…»: гілка «довільний текст» шле ще й Ірі, а ЗАЯВКА/«МК: видано»
йдуть у NOTIFY_IDS, де Іра. Тепер: адмін і id з позначкою «акаунт Yaro» (LYUDY_MARKS) не будять Іру ні текстом,
ні файлом, ні ЗАЯВКОЮ, ні «Новий у боті»; Yaro отримує як і раніше; справжні люди (і «друг Yaro») йдуть Ірі.
Дві розкладки: Іра у NOTIFY_IDS (1,2) і Іра лише IRA_ID (NOTIFY_IDS=1). Запуск: python -B test_yaro_ne_ira.py
"""
import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "555:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "NOTIFY_IDS": "1,2", "IRA_ID": "2", "IRA_ON": "1",
                   "MAGNET_URL": "MAGNIT", "START_PIC": "PIC_START", "CHANNEL_URL": "https://t.me/test_kanal",
                   "LYUDY_MARKS": "686405950:акаунт Yaro,674792338:друг Yaro"})
for _k in ("DATABASE_URL", "LEAD_IDS", "PUSH_SKIP_IDS"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    method = url.rsplit("/", 1)[-1]
    p = dict(json or data or {})
    mid = 1000 + len(VYKLYKY)
    VYKLYKY.append((method, p))
    if method == "getChat":
        return _R({"ok": True, "result": {"id": p.get("chat_id"), "type": "private", "first_name": "Чат"}})
    return _R({"ok": True, "result": {"message_id": mid}})


requests.post = fake_post
import bot
import store
from datetime import datetime, timezone

DB = {"kv": {}, "events": [], "users": {}}


def touch_user(u, role="client", source_tag=None):
    uid = u.get("id")
    new = uid not in DB["users"]
    DB["users"][uid] = dict(DB["users"].get(uid, {}), user_id=uid, username=u.get("username"),
                            first_name=u.get("first_name"), last_name=u.get("last_name"))
    return dict(DB["users"][uid], is_new=new)


def kv_set(k, v):
    DB["kv"][k] = str(v)


def kv_claim(k):
    if k in DB["kv"]:
        return False
    DB["kv"][k] = "1"
    return True


store.ON = True
store.q = lambda *a, **k: None
store.kv_get = lambda k, default=None: DB["kv"].get(k, default)
store.kv_set = kv_set
store.kv_claim = kv_claim
store.log_event = lambda uid, kind, payload=None: DB["events"].append((uid, kind, payload))
store.touch_user = touch_user
store.get_user = lambda uid: DB["users"].get(uid)
store.add_purchase = lambda *a, **k: None
store.wipe_user = lambda uid: None
bot.kabinet_mist.push_user = lambda uid: None
bot.bg = lambda fn, *a, **k: fn(*a, **k)
bot._alb_spawn[0] = lambda fn, *a: None
bot.time.sleep = lambda s: None

app = bot.app.test_client()
PADINNIA = []
ADMIN, IRA = 1, 2
INCOG, VADIM, OLIA = 686405950, 674792338, 777000


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


MID = [100]


def msg(uid, **kw):
    MID[0] += 1
    VYKLYKY.clear()
    m = dict({"message_id": MID[0], "chat": {"id": uid, "type": "private"},
              "from": {"id": uid, "first_name": "S" + str(uid), "username": "u" + str(uid)}}, **kw)
    app.post("/sekret", json={"message": m})
    return list(VYKLYKY)


def cb(uid, data):
    VYKLYKY.clear()
    app.post("/sekret", json={"callback_query": {"id": "c", "data": data,
                                                 "from": {"id": uid, "first_name": "S" + str(uid)},
                                                 "message": {"message_id": 99, "chat": {"id": uid}}}})
    return list(VYKLYKY)


def to(vv, chat, methods=("sendMessage", "forwardMessage")):
    """Службові виклики в чат персоналу (не відповіді людині в її чат)."""
    return [(m, p) for m, p in vv if m in methods and p.get("chat_id") == chat]


def txt(vv, chat):
    return [p.get("text") or "" for m, p in to(vv, chat, ("sendMessage",))]


def nova():
    DB["kv"].clear()
    DB["users"].clear()
    DB["events"].clear()


for ROZKLADKA, NOTIFY in (("Іра у NOTIFY_IDS", [ADMIN, IRA]), ("Іра лише IRA_ID", [ADMIN])):
    print("\n=== " + ROZKLADKA + " ===")
    bot.NOTIFY_IDS = list(NOTIFY)
    bot.LEAD_IDS = list(NOTIFY)
    nova()

    ok("yaro_account: адмін, акаунт Yaro; не друг, не Іра, не людина",
       bot.yaro_account(ADMIN) and bot.yaro_account(INCOG) and not bot.yaro_account(VADIM)
       and not bot.yaro_account(IRA) and not bot.yaro_account(OLIA) and not bot.yaro_account(0))

    # 1. Пастка Git Bash: текст «C:/Program Files/Git/nova» від адміна
    vv = msg(ADMIN, text="C:/Program Files/Git/nova")
    ok("адмін, текст не команда: Іра нічого", not to(vv, IRA), str(to(vv, IRA))[:200])
    ok("адмін, текст не команда: Yaro отримав сповіщення",
       any("Program Files" in t for t in txt(vv, ADMIN)), str(txt(vv, ADMIN))[:200])

    # 2. Другий акаунт Yaro (позначка): текст
    vv = msg(INCOG, text="Привіт, це тест")
    ok("акаунт Yaro (позначка), текст: Іра нічого", not to(vv, IRA), str(to(vv, IRA))[:200])
    ok("акаунт Yaro (позначка), текст: Yaro отримав",
       any("Привіт, це тест" in t for t in txt(vv, ADMIN)), str(txt(vv, ADMIN))[:200])

    # 3. ЗАЯВКА від кліку «Курс ретуші» (pick_product k12z)
    vv = cb(INCOG, "k12z")
    ok("акаунт Yaro, ЗАЯВКА: Іра нічого", not to(vv, IRA), str(to(vv, IRA))[:200])
    ok("акаунт Yaro, ЗАЯВКА: Yaro отримав",
       any(t.startswith("Дивиться") for t in txt(vv, ADMIN)), str(txt(vv, ADMIN))[:200])
    vv = cb(ADMIN, "k12z")
    ok("адмін, ЗАЯВКА: Іра нічого", not to(vv, IRA), str(to(vv, IRA))[:200])

    # 4. Файл від акаунта Yaro: пересилка Ірі не йде, Yaro отримує
    vv = msg(INCOG, photo=[{"file_id": "F1", "file_unique_id": "u1"}], caption="до/після")
    ok("акаунт Yaro, фото: Іра нічого", not to(vv, IRA), str(to(vv, IRA))[:200])
    ok("акаунт Yaro, фото: Yaro отримав підпис і пересилку",
       any(m == "forwardMessage" for m, p in to(vv, ADMIN)) and any("Від " in t for t in txt(vv, ADMIN)),
       str(to(vv, ADMIN))[:200])

    # 5. Справжня людина і «друг Yaro»: Іра отримує, як і раніше
    for kto, nazva in ((OLIA, "людина"), (VADIM, "друг Yaro")):
        vv = msg(kto, text="а де урок?")
        ok(nazva + ", текст: Іра отримала", any("а де урок?" in t for t in txt(vv, IRA)), str(to(vv, IRA))[:200])
        ok(nazva + ", текст: Yaro отримав", any("а де урок?" in t for t in txt(vv, ADMIN)))
        ok(nazva + ", текст: рівно одне сповіщення Ірі (без дубля)",
           len([t for t in txt(vv, IRA) if "а де урок?" in t]) == 1, str(txt(vv, IRA))[:200])
        vv = cb(kto, "k12z")
        ok(nazva + ", ЗАЯВКА: Іра отримала",
           ROZKLADKA != "Іра у NOTIFY_IDS" or any(t.startswith("Дивиться") for t in txt(vv, IRA)),
           str(txt(vv, IRA))[:200])
        vv = msg(kto, photo=[{"file_id": "F2", "file_unique_id": "u2"}], caption="ось")
        ok(nazva + ", фото: Іра отримала пересилку", any(m == "forwardMessage" for m, p in to(vv, IRA)),
           str(to(vv, IRA))[:200])

    # 6. Кнопки «Написати/Подарунок» у Yaro про людину на місці
    vv = msg(OLIA, text="ще питання")
    n = [p for m, p in to(vv, ADMIN, ("sendMessage",)) if "ще питання" in (p.get("text") or "")]
    kn = [b.get("callback_data") for r in (n[0].get("reply_markup") or {}).get("inline_keyboard", []) for b in r] if n else []
    ok("Yaro: кнопки napys/podar під сповіщенням про людину", kn[-2:] == ["napys:777000", "podar:777000"], str(kn))

# 7. Умови: Іра як uid не страждає, IRA_ID=0 (не задано) не ламає
bot.NOTIFY_IDS = [ADMIN]
bot.LEAD_IDS = [ADMIN]
ok("_without_ira: людина, список не міняється", bot._without_ira([1, 2], OLIA) == [1, 2])
ok("_without_ira: акаунт Yaro, Іру прибрано", bot._without_ira([1, 2], INCOG) == [1])
ok("_without_ira: без цілі нічого не міняє", bot._without_ira([1, 2], None) == [1, 2])
_ira = bot.IRA_ID
bot.IRA_ID = 0
ok("_without_ira: IRA_ID не задано, список цілий", bot._without_ira([1, 2], INCOG) == [1, 2])
bot.IRA_ID = _ira

print("\nПАДІННЯ: " + str(PADINNIA) if PADINNIA else "\nУсе зелене")
sys.exit(1 if PADINNIA else 0)
