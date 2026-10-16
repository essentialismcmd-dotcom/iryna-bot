#!/usr/bin/env python3
"""Воронка після реклами (гілка voronka 16.10, VORONKA-2026-10.md п.1, 4-6, 10) БЕЗ мережі і бази:
подарунок лише за підписку («Я підписалась» → getChatMember), Т4 після уроку, Т5 на день 1,
ворота ціни для холодних (Т9 → «Розкажіть про курс» → картка), теплі входи без воріт,
GUIDE_PRICE/GUIDE_OLD_PRICE у картці гайда."""
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
import bot, store
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

# ---- п.1: перший екран і «Я підписалась»
user_obj[777] = user(777)
msg(777, "/start retush_ig")
m = msgs(777)
ok("вхід: одне повідомлення", len(m) == 1, len(m))
ok("Т1: подарунок за підписку, без ціни", "«Я підписалась»" in texts(777)[0] and not has_price(texts(777)[0]))
ok("кнопки: урок, канал (окреме запрошення), «Я підписалась»",
   names(m[0]) == ["Відкрити урок", "Канал «для своїх»", "Я підписалась"]
   and btns(m[0])[1]["url"] == "https://t.me/+retush-invite", names(m[0]))

V.clear(); MEMBER[777] = "left"
cb(777, "sub:check")
ok("не в каналі: Т2, файла нема", texts(777) == [bot.SUB_NO] and not docs(777), texts(777))
ok("Т2 з кнопками канал + «Я підписалась»", names(msgs(777)[0]) == ["Канал «для своїх»", "Я підписалась"])
ok("getChatMember питали без кешу", any(m == "getChatMember" and p.get("user_id") == 777 for m, p in V))

V.clear(); MEMBER[777] = "member"
cb(777, "sub:check")
ok("в каналі: Т3 + файл", texts(777)[0] == bot.GIFT_SUB and len(docs(777)) == 1, texts(777))
ok("кеш не завадив (свіжа відповідь «так»)", True)
ok("події sub_ok і magnet via gift", any(e[1] == "sub_ok" for e in EV) and any(e[1] == "magnet" for e in EV))
ok("kv gift:777 і sub_ok:777", KV.get("gift:777") and KV.get("sub_ok:777"))

V.clear()
cb(777, "sub:check")
ok("вдруге: «уже у вас», другого файла нема", texts(777) == [bot.SUB_ALREADY] and not docs(777), texts(777))

# ---- невідомо (бот не адмін): людині «подивлюсь сама», персоналу кнопка подарунка
user_obj[790] = user(790); MEMBER[790] = "err"; V.clear()
cb(790, "sub:check")
ok("невідомо: Т «подивлюсь сама» з кнопками", texts(790) == [bot.SUB_UNKNOWN] and "Я підписалась" in names(msgs(790)[0]), texts(790))
st = [p for m, p in V if m == "sendMessage" and p.get("chat_id") == 1]
ok("персоналу сповіщення з «🎁 Подарунок»", st and "podar:790" in json.dumps(st[-1].get("reply_markup")), st)
ok("файла не було", not docs(790))

# ---- п.1: done уроку 1.5 з кабінету
user_obj[778] = user(778); MEMBER[778] = "left"; V.clear()
r = c.post("/kabinet-podiia", json={"user_id": 778, "kind": "done", "lesson": "1.5", "min": 12}, headers=H)
ok("done НП: 200", r.status_code == 200, r.status_code)
ok("done НП: Т4 з рядком про підписку, без файла", texts(778) == [bot.GIFT_DONE_NOSUB] and not docs(778), texts(778))
ok("done НП: кнопки канал + «Я підписалась»", names(msgs(778)[0]) == ["Канал «для своїх»", "Я підписалась"])

user_obj[779] = user(779); MEMBER[779] = "member"; V.clear()
c.post("/kabinet-podiia", json={"user_id": 779, "kind": "done", "lesson": "1.5"}, headers=H)
ok("done П без подарунка: Т4 + файл", texts(779)[0] == bot.GIFT_DONE and len(docs(779)) == 1, texts(779))

V.clear()
c.post("/kabinet-podiia", json={"user_id": 777, "kind": "done", "lesson": "1.5"}, headers=H)
ok("done тій, що вже має файл: лише питання про урок", texts(777) == [bot.GIFT_DONE_ASK] and not docs(777), texts(777))

# ---- Т5 день 1 (gift_late_run)
from datetime import datetime, timezone
NOON = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)     # 12:00 Київ
calls = []
user_obj[783] = user(783); user_obj[784] = user(784); MEMBER[783] = "left"; MEMBER[784] = "member"
def _cand(since, after_h, skip, skip_kv=None):
    calls.append(skip_kv)
    return [u for u in (783, 784) if not KV.get((skip_kv or "") + str(u))]
store.gift_candidates = _cand
V.clear()
n = bot.gift_late_run(NOON)
ok("день 1: двом по одній дії", n == 2, n)
ok("кандидатів брали без уже нагаданих (skip_kv)", calls == ["gift_remind:"], calls)
ok("НП: Т5 з кнопками урок, канал, «Я підписалась», без файла",
   texts(783) == [bot.GIFT_REMIND] and names(msgs(783)[0]) == ["Відкрити урок", "Канал «для своїх»", "Я підписалась"]
   and not docs(783), texts(783))
ok("П без кнопки: файл Т3", texts(784)[0] == bot.GIFT_SUB and len(docs(784)) == 1, texts(784))
V.clear()
ok("другий прогін нікого не чіпає", bot.gift_late_run(NOON) == 0 and not msgs(783) and not msgs(784))
ok("поза 10-20 Києва нічого", bot.gift_late_run(datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)) == 0)

# ---- п.4-6: ворота ціни
user_obj[780] = user(780, "retush_liza"); V.clear()
msg(780, "курс")
ok("холодна пише «курс»: Т9 без ціни", texts(780) == [bot.ZAPR_TEXT] and not has_price(texts(780)[0]), texts(780))
ok("кнопки «Розкажіть про курс» + канал", names(msgs(780)[0]) == ["Розкажіть про курс", "Канал «для своїх»"], names(msgs(780)[0]))
ok("подія gate", any(e == (780, "gate", None) for e in EV))
V.clear()
r = c.post("/kabinet-kupyty", json={"user_id": 780}, headers=H)
ok("кнопка «Весь курс» з кабінету холодній: Т9, не картка", r.status_code == 200 and texts(780) == [bot.ZAPR_TEXT], texts(780))
V.clear()
cb(780, "retush")
ok("кнопка «Курс ретуші» холодній: Т9", texts(780) == [bot.ZAPR_TEXT], texts(780))
V.clear()
cb(780, "zapr:open")
t = texts(780)
ok("«Розкажіть про курс»: картка з ціною і кодом", len(t) == 1 and has_price(t[0]) and "IR" in t[0], t)
ok("kv zapr:780 і подія zapr_open", KV.get("zapr:780") == "1" and any(e[1] == "zapr_open" for e in EV))
V.clear()
msg(780, "курс")
ok("після згоди «курс» дає картку з ціною", texts(780) and has_price(texts(780)[0]), texts(780))
V.clear()
c.post("/kabinet-kupyty", json={"user_id": 780}, headers=H)
ok("і кнопка з кабінету теж картку", texts(780) and has_price(texts(780)[0]), texts(780))

# ---- теплі входи без воріт
user_obj[781] = user(781); V.clear()
msg(781, "/start kurs10")
ok("/start kurs10 холодній за міткою: картка зі знижкою одразу", texts(781) and has_price(texts(781)[0]), texts(781))
user_obj[782] = user(782, "guide"); V.clear()
msg(782, "курс")
ok("людина з гайда (не retush): картка одразу", texts(782) and has_price(texts(782)[0]), texts(782))
user_obj[785] = user(785); V.clear()
msg(785, "/kurs")
ok("/kurs: картка без воріт", texts(785) and has_price(texts(785)[0]), texts(785))

# ---- гайд 199 замість 900
ok("GUIDE_PRICE=199: кнопка і картка", bot.TIERS["t1"]["btn"] == "Гайд, 199 грн"
   and bot.TIERS["t1"]["text"].startswith("Гайд «Світло», 199 грн замість 900\n\n"), bot.TIERS["t1"]["text"][:60])
ok("PRODUCTS t1 на 199 (банка звіряє цю суму)", bot.PRODUCTS["t1"]["uah"] == 199)

# ---- прапорці
ok("GIFT_FOR_SUB і PRICE_GATE увімкнені за замовчуванням", bot.GIFT_FOR_SUB and bot.PRICE_GATE)
ok("sub:check і zapr:open під блокуванням на користувача", "sub:check" in bot._LOCKED_CB and "zapr:open" in bot._LOCKED_CB)

print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
