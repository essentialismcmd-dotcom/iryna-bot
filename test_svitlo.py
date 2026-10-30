#!/usr/bin/env python3
"""Входи ?start=svitlo (реклама) і ?start=profil (шапка Instagram), гілка svitlo 16.10: привіт про три схеми,
«Канал» + «Я підписалась», файл після живого sub:check, без уроку ретуші і ціни, далі Д2 (гайд). БЕЗ мережі і бази."""
import os, sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1", "COURSES_ON": "1", "COURSE_BUNDLE_ONLY": "1",
                   "PAY_URL": "https://send.monobank.ua/jar/test", "NOTIFY_IDS": "1",
                   "KABINET_URL": "https://kab.test/", "KABINET_KEY": "test-key",
                   "CHANNEL_URL": "https://t.me/iryna_rul_photographer",
                   "CHANNEL_URL_RETUSH": "https://t.me/+retush-invite",
                   "MAGNET_URL": "https://files.test/magnit.pdf",
                   "GUIDE_PRICE": "199", "GUIDE_OLD_PRICE": "900"})
os.environ.pop("DATABASE_URL", None)
import requests
V = []
MEMBER = {}          # uid -> статус у каналі для getChatMember; "err" = Telegram відмовив
class _R:
    def __init__(s, j): s._j = j; s.status_code = 200
    def json(s): return s._j
def fake_post(url, json=None, data=None, files=None, timeout=None, headers=None):
    m = url.rsplit("/", 1)[-1]
    p = json or data or {}
    V.append((m, p))
    if m == "getChatMember":
        st = MEMBER.get(p.get("user_id"), "left")
        if st == "err":
            return _R({"ok": False, "description": "Bad Request: not enough rights"})
        return _R({"ok": True, "result": {"status": st}})
    return _R({"ok": True, "result": {"message_id": len(V)}})
requests.post = fake_post
os.environ["FREE_LESSON"] = "1"   # 19.10: магніт уроку вимкнено за замовчуванням, тут перевіряємо його самого
import bot, store
bot.TOUCH_D2_ON = True
KV, USERS, EV, MAGNET = {}, {}, [], set()
store.kv_get = lambda k, d=None: KV.get(k, d)
store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
def _claim(k):
    if k in KV:
        return False
    KV[k] = "1"
    return True
store.kv_claim = _claim
store.get_user = lambda uid: dict(USERS.get(uid) or {}, got_magnet_at=("x" if uid in MAGNET else None)) if uid in USERS else None
store.purchases_of = lambda uid, only_paid=True: []
store.log_event = lambda uid, kind, payload=None: EV.append((uid, kind, payload))
store.mark_magnet = lambda uid: MAGNET.add(uid)
c = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
def msgs(uid): return [p for m, p in V if p.get("chat_id") == uid and m in ("sendMessage", "sendPhoto", "sendDocument")]
def texts(uid): return [(p.get("text") or p.get("caption") or "") for p in msgs(uid)]
def docs(uid): return [p for m, p in V if m == "sendDocument" and p.get("chat_id") == uid]
def btns(p):
    rm = p.get("reply_markup") or {}
    rm = json.loads(rm) if isinstance(rm, str) else rm
    return [b for r in rm.get("inline_keyboard", []) for b in r]
def names(p): return [b["text"] for b in btns(p)]
def user(uid, tag="retush_ig"):
    USERS[uid] = {"user_id": uid, "username": "u%d" % uid, "first_name": "Тест", "source_tag": tag}
    return {"id": uid, "first_name": "Тест", "username": "u%d" % uid}
def msg(uid, text):
    c.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": uid}, "from": user_obj[uid], "text": text}})
def cb(uid, data):
    c.post("/sekret", json={"callback_query": {"id": "q", "data": data, "from": user_obj[uid],
                                               "message": {"message_id": 5, "chat": {"id": uid}}}})
user_obj = {}
H = {"X-Kabinet-Key": "test-key"}
PRICE_WORDS = ("грн", "3300", "3 300", "2970", "2 970")
def has_price(t): return any(w in t for w in PRICE_WORDS)
from datetime import datetime, timezone
NOON = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
def start(uid, tag):
    user_obj[uid] = {"id": uid, "first_name": "Тест", "username": "u%d" % uid}
    USERS[uid] = {"user_id": uid, "username": "u%d" % uid, "first_name": "Тест", "source_tag": tag}
    V.clear(); msg(uid, "/start " + tag)

for i, tag in enumerate(("svitlo", "profil")):
    uid = 800 + i
    start(uid, tag); m = msgs(uid)
    t = texts(uid)[0] if m else ""
    ok(tag + ": одне повідомлення з привітом", len(m) == 1 and t == bot.SVITLO_HELLOS[tag], texts(uid))
    ok(tag + ": дослівно з TEKST.md п.5", "Привіт, це Іра ♥️" in t and "«Три схеми світла з одного сетапу»" in t and t.endswith("і файл прийде сюди."), t)
    ok(tag + ": про схеми світла, без уроку, курсу і ціни", "схеми світла" in t and "урок" not in t.lower()
       and "курс" not in t.lower() and not has_price(t), t)
    ok(tag + ": кнопки «Канал» + «Я підписалась»", names(m[0]) == ["Канал «для своїх»", "Я підписалась"], names(m[0]))
    ok(tag + ": файла до підписки нема", not docs(uid) and uid not in MAGNET)
    ok(tag + ": подія svitlo_entry з міткою", (uid, "svitlo_entry", {"tag": tag}) in EV, EV[-3:])
    ok(tag + ": мітка в source_tag (лічильники /stats, /lyudy)", USERS[uid]["source_tag"] == tag)
    if tag == "profil": ok("profil: свій текст про профіль", "з мого профілю" in t and "з мого профілю" not in bot.SVITLO_HELLO)
    V.clear(); MEMBER[uid] = "left"; cb(uid, "sub:check")
    ok(tag + ": не в каналі: Т2, файла нема, кнопки канал + «Я підписалась»",
       texts(uid) == [bot.SUB_NO] and not docs(uid) and names(msgs(uid)[0]) == ["Канал «для своїх»", "Я підписалась"], texts(uid))
    ok(tag + ": канал у кнопці звичайний (не запрошення ретуші)",
       [b.get("url") for b in btns(msgs(uid)[0])][0] == "https://t.me/iryna_rul_photographer", btns(msgs(uid)[0]))
    V.clear(); MEMBER[uid] = "member"; cb(uid, "sub:check")
    ok(tag + ": в каналі: Т3 + файл (v3d, magnet_ref)", texts(uid)[0] == bot.GIFT_SUB and len(docs(uid)) == 1 and uid in MAGNET, texts(uid))
    ok(tag + ": подія sub_ok", (uid, "sub_ok", None) in EV)

# окреме запрошення на мітку
os.environ["CHANNEL_URL_PROFIL"] = "https://t.me/+profil-invite"
start(810, "profil")
ok("CHANNEL_URL_PROFIL: кнопка веде в запрошення шапки", btns(msgs(810)[0])[0].get("url") == "https://t.me/+profil-invite")
start(811, "svitlo")
ok("svitlo без свого запрошення: загальний канал", btns(msgs(811)[0])[0].get("url") == "https://t.me/iryna_rul_photographer")
del os.environ["CHANNEL_URL_PROFIL"]

# ретуш не зачеплена
start(820, "retush"); ok("retush: як раніше, одна кнопка «Відкрити урок»", names(msgs(820)[0]) == ["Відкрити урок"], names(msgs(820)[0]))
start(821, "svitlox"); ok("невідома мітка: загальне HELLO", texts(821) == [bot.HELLO], texts(821))

# дотики: Д1 для svitlo без файла без уроку; Д2 тим, хто має подарунок
CAND = {"d1": [830, 831], "d2": [800, 801]}
def _tc(since, lo, hi, skip, skip_kv, with_gift=False, any_tag=False):
    return [(u, ("x" if with_gift else None)) for u in CAND["d2" if with_gift else "d1"] if not KV.get(skip_kv + str(u))]
store.touch_candidates = _tc
store.user_texts = lambda uid: ""
start(830, "svitlo"); start(831, "profil"); KV["gift:831"] = "1"
for u_ in (800, 801): KV.pop("hajd199:%d" % u_, None)
V.clear(); EV.clear()
n = bot.touch_run(NOON)
ok("Д1 svitlo без файла: нагадування без уроку", texts(830) == [bot.SVITLO_REMIND] and "урок" not in texts(830)[0].lower()
   and names(msgs(830)[0]) == ["Канал «для своїх»", "Я підписалась"], texts(830))
ok("Д1 profil з подарунком: нічого", msgs(831) == [])
ok("Д2 svitlo/profil з подарунком: в особисті, без ціни", all([(b["text"], b.get("url")) for b in btns(msgs(u_)[0])] == [("Написати помічниці", bot.dm_url(bot.TOUCH_D2_PERSHE))]
   and "грн" not in texts(u_)[0] and "@iryna_rul_studio" in texts(u_)[0] for u_ in (800, 801)), [texts(800), texts(801)])   # 29.10 Yaro: Д2 кличе в розмову
ok("Д2: події hajd199 по обох", all(any(e[:2] == (u_, "hajd199") for e in EV) for u_ in (800, 801)))

# /lyudy: рядок по мітках
rows = [{"marks": [], "stage": "схеми", "tag": "svitlo", "schemes": True, "guide": False, "kanal": (True, "")},
        {"marks": [], "stage": "старт", "tag": "svitlo", "schemes": False, "guide": False, "kanal": (False, "")},
        {"marks": [], "stage": "гайд", "tag": "profil", "schemes": True, "guide": True, "kanal": (True, "")}]
ln = bot._svitlo_line(rows)
ok("/lyudy: svitlo 2/1/1/0; profil 1/1/1/1; storis 0; svit 0; hajd299 0", ln == "svitlo 2 / 1 / 1 / 0; profil 1 / 1 / 1 / 1; storis 0 / 0 / 0 / 0; svit 0 / 0 / 0 / 0; hajd299 0 / 0 / 0 / 0", ln)

# 17.10: ?start=hajd299 (реклама гайда 299): одразу картка гайда з тарифами, подія guide_entry
start(840, "hajd299"); m = msgs(840)
ok("hajd299: одна картка гайда, як на слово «гайд»", len(m) == 1 and texts(840)[0] == bot.guide_intro(bot.tiers_kb())
   and names(m[0]) == names({"reply_markup": bot.tiers_kb()}), texts(840))
ok("hajd299: подія guide_entry з міткою", (840, "guide_entry", {"tag": "hajd299"}) in EV, EV[-3:])
ok("hajd299: не магніт і не svitlo", texts(840)[0] not in (bot.HELLO, bot.SVITLO_HELLO))
ok("LYUDY_KINDS знає svitlo_entry", "svitlo_entry" in bot.LYUDY_KINDS)
import inspect, store as _s
ok("store.touch_candidates бере svitlo і profil", "'svitlo', 'profil', 'storis', 'svit'" in inspect.getsource(_s.touch_candidates) if hasattr(_s.touch_candidates, "__code__") and _s.touch_candidates.__name__ != "_tc" else True)

print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
