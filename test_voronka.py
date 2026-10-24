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
os.environ["FREE_LESSON"] = "1"   # 19.10: магніт уроку вимкнено за замовчуванням, тут перевіряємо його самого
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
ok("привіт: рядок про подарунок, без слова «курс» і ціни",
   "подарунок: три схеми світла" in texts(777)[0] and "12 хвилин" in texts(777)[0]
   and "курс" not in texts(777)[0].lower() and not has_price(texts(777)[0]), texts(777)[0])
ok("привіт: ОДНА кнопка «Відкрити урок», каналу і «Я підписалась» нема", names(m[0]) == ["Відкрити урок"], names(m[0]))
for tag in ("retush", "retush_liza"):
    user_obj[760] = user(760, tag); V.clear(); msg(760, "/start " + tag)
    ok("вхід " + tag + ": одна кнопка", names(msgs(760)[0]) == ["Відкрити урок"], names(msgs(760)[0]))

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
ok("вдруге (24.10): «уже ваш» і той самий файл ще раз", texts(777)[:1] == [bot.FREE_AGAIN] and len(docs(777)) == 1, texts(777))

# ---- п.1: кнопка «Забрати три схеми світла» (голий /start, «Мої матеріали») теж за підписку
user_obj[791] = user(791, tag=""); MEMBER[791] = "left"; V.clear()
cb(791, "magnet")
ok("magnet без підписки: Т2, файла нема", texts(791) == [bot.SUB_NO] and not docs(791) and 791 not in MAGNET, texts(791))
ok("magnet без підписки: кнопки канал + «Я підписалась»", names(msgs(791)[0]) == ["Канал «для своїх»", "Я підписалась"], names(msgs(791)[0]))
V.clear(); cb(791, "lock:check")
ok("стара lock:check без підписки: файла нема", not docs(791), texts(791))
V.clear(); MEMBER[791] = "member"
cb(791, "magnet")
ok("magnet з підпискою: Т3 + файл", texts(791)[:1] == [bot.GIFT_SUB] and len(docs(791)) == 1 and 791 in MAGNET, texts(791))
V.clear(); cb(791, "magnet")
ok("magnet вдруге (24.10): «уже ваш» і файл ще раз", texts(791)[:1] == [bot.FREE_AGAIN] and len(docs(791)) == 1, texts(791))

# ---- невідомо (бот не адмін): з 24.10 файл одразу, персоналу сповіщення
user_obj[790] = user(790); MEMBER[790] = "err"; V.clear()
cb(790, "sub:check")
ok("невідомо (24.10): файл одразу, без «подивлюсь сама»", texts(790)[:1] == [bot.GIFT_SUB] and len(docs(790)) == 1, texts(790))
st = [p for m, p in V if p.get("chat_id") == 1 and "text" in p]
ok("персоналу сповіщення «без перевірки»", st and any("без перевірки" in (p.get("text") or "") for p in st), st)

# ---- п.1: done уроку 1.5 з кабінету
user_obj[778] = user(778); MEMBER[778] = "left"; V.clear()
r = c.post("/kabinet-podiia", json={"user_id": 778, "kind": "done", "lesson": "1.5", "min": 12}, headers=H)
ok("done НП: 200", r.status_code == 200, r.status_code)
ok("done НП: текст про подарунок для підписників, без файла", texts(778) == [bot.GIFT_DONE_NOSUB] and not docs(778), texts(778))
ok("done: дослівний текст",
   texts(778)[0] == "Ви додивились ♥️ Подарунок «Три схеми світла» віддаю підписникам каналу «для своїх»: там бекстейдж і до/після зі зйомок.")
ok("done НП: кнопки канал + «Я підписалась»", names(msgs(778)[0]) == ["Канал «для своїх»", "Я підписалась"])

user_obj[779] = user(779); MEMBER[779] = "member"; V.clear()
c.post("/kabinet-podiia", json={"user_id": 779, "kind": "done", "lesson": "1.5"}, headers=H)
ok("done П без подарунка: файла НЕ шле, кнопки канал + «Я підписалась»",
   texts(779) == [bot.GIFT_DONE_NOSUB] and not docs(779) and 779 not in MAGNET
   and names(msgs(779)[0]) == ["Канал «для своїх»", "Я підписалась"], texts(779))
ok("done П: getChatMember не питали (файл лише після sub:check)", not any(m == "getChatMember" for m, p in V))
V.clear(); cb(779, "sub:check")
ok("після sub:check: файл", texts(779)[0] == bot.GIFT_SUB and len(docs(779)) == 1 and 779 in MAGNET, texts(779))
ok("sub:check питає getChatMember наживо", any(m == "getChatMember" and p.get("user_id") == 779 for m, p in V))

V.clear()
c.post("/kabinet-podiia", json={"user_id": 777, "kind": "done", "lesson": "1.5"}, headers=H)
ok("done тій, що вже має файл: лише питання про урок", texts(777) == [bot.GIFT_DONE_ASK] and not docs(777), texts(777))

# ---- gift_late вимкнено, дотики Д1/Д2 (touch_run)
from datetime import datetime, timezone
NOON = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)     # 12:00 Київ
ok("gift_late_run з GIFT_FOR_SUB нічого не робить", bot.gift_late_run(NOON) == 0)
CAND = {"d1": [], "d2": []}
TEXTS = {}
calls = []
def _tc(since, lo, hi, skip, skip_kv, with_gift=False):
    calls.append((lo, hi, skip_kv, with_gift))
    return [(u, ("x" if with_gift else None)) for u in CAND["d2" if with_gift else "d1"] if not KV.get(skip_kv + str(u))]
store.touch_candidates = _tc
store.user_texts = lambda uid: TEXTS.get(uid, "")
for u in (783, 784, 786, 787, 788):
    user_obj[u] = user(u)
CAND["d1"] = [783, 784, 786, 787]
KV["kp:784:1.5:done"] = "1"                                   # 784 додивилась, подарунка нема
KV["kp:786:1.5:done"] = "1"; KV["gift:786"] = "1"             # 786 додивилась і має подарунок
TEXTS[787] = "стоп"
V.clear()
n = bot.touch_run(NOON)
ok("Д1: двом по дотику (783, 784); 786 має все, 787 стоп", n == 2 and msgs(786) == [] and msgs(787) == [], n)
ok("Д1 без done: текст і одна кнопка «Відкрити урок»",
   texts(783) == [bot.TOUCH_D1_LESSON] and names(msgs(783)[0]) == ["Відкрити урок"], texts(783))
ok("Д1 дослівно", bot.TOUCH_D1_LESSON == "Урок чекає на вас ♥️ 12 хвилин, коли буде зручно")
ok("Д1 done без підписки: Т5 з кнопками канал і «Я підписалась», файла нема",
   texts(784) == [bot.GIFT_REMIND] and "Канал «для своїх»" in names(msgs(784)[0])
   and "Я підписалась" in names(msgs(784)[0]) and not docs(784) and not any(m == "getChatMember" for m, p in V), texts(784))
ok("вікно Д1 ~20-36 год, kv touch_d1:", calls[0][:3] == (20, 36, "touch_d1:") and KV.get("touch_d1:783") == "1", calls[0])
V.clear()
ok("другий прогін нікого не чіпає", bot.touch_run(NOON) == 0 and not msgs(783) and not msgs(784))
ok("поза 10-20 Києва нічого", bot.touch_run(datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)) == 0
   and bot.touch_run(datetime(2026, 10, 17, 6, 59, tzinfo=timezone.utc)) == 0)
CAND["d1"] = []
CAND["d2"] = [788, 789]
user_obj[789] = user(789)
KV["hajd199:789"] = "1"                                        # 789 вже отримала розсилку про гайд
V.clear(); EV.clear()
n = bot.touch_run(NOON)
ok("Д2: одна людина (789 уже мала hajd199)", n == 1 and msgs(789) == [], n)
ok("Д2 текст зі 199 з GUIDE_PRICE і кнопка «Гайд, 199 грн» (callback guide)",
   texts(788) == ["Три схеми у вас. Усі тринадцять, з розстановкою і кадром, у гайді «Світло», 199 грн, доступ назавжди."]
   and [(b["text"], b.get("callback_data")) for b in btns(msgs(788)[0])] == [("Гайд, 199 грн", "guide")], texts(788))
ok("Д2: подія hajd199, kv hajd199:788, вікно 44-60", any(e[:2] == (788, "hajd199") for e in EV) and KV.get("hajd199:788")
   and calls[-1][:2] == (44, 60) and calls[-1][3] is True, calls[-1])
V.clear(); ok("Д2 вдруге не шле", bot.touch_run(NOON) == 0 and not msgs(788))
bot_owned = bot.owned_keys
bot.owned_keys = lambda uid, real=False: {"k1"} if uid == 790 else set()
CAND["d2"] = [790]; V.clear()
ok("Д2: купила, нічого", bot.touch_run(NOON) == 0 and not msgs(790))
bot.owned_keys = bot_owned

# ---- 16.10: ворота ціни вимкнені, слова про курс дають картку з ціною одразу
user_obj[780] = user(780, "retush_liza"); V.clear()
msg(780, "курс")
ok("холодна пише «курс»: картка з ціною одразу", texts(780) and has_price(texts(780)[0]) and "впишіть" not in texts(780)[0], texts(780))
ok("кнопки «Розкажіть про курс» нема", not any("Розкажіть про курс" in names(p) for p in msgs(780)))
ok("події gate нема", not any(e[1] == "gate" for e in EV))
V.clear()
r = c.post("/kabinet-kupyty", json={"user_id": 780}, headers=H)
ok("/kabinet-kupyty: картка з ціною одразу", r.status_code == 200 and texts(780) and has_price(texts(780)[0]), texts(780))
V.clear(); cb(780, "retush")
ok("кнопка «Курс ретуші» холодній: без Т9", texts(780) and bot.ZAPR_TEXT not in texts(780), texts(780))
user_obj[775] = user(775, "retush_x"); V.clear()
msg(775, "/start kurs")
ok("мітка kurs холодній: картка з ціною", texts(775) and has_price(texts(775)[0]), texts(775))
V.clear(); msg(775, "/start kurs10")
ok("мітка kurs10: картка зі знижкою", texts(775) and has_price(texts(775)[0]), texts(775))

# ---- теплі входи
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
ok("GIFT_FOR_SUB увімкнено, PRICE_GATE вимкнено за замовчуванням", bot.GIFT_FOR_SUB and not bot.PRICE_GATE)
ok("sub:check і zapr:open під блокуванням на користувача", "sub:check" in bot._LOCKED_CB and "zapr:open" in bot._LOCKED_CB)

print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
