#!/usr/bin/env python3
"""Матриця шляхів людини 08.10 (БЕЗ мережі і бази): мітки, липкість, слова, кнопки.
Інваріанти: людина з retush/kurs/kurs10 не бачить світла, поки сама не попросила;
кожна картка курсу 3300 + знижка 2970 (-7); без «скоро»/порожніх; українською; у магнітах нема ціни."""
import os, sys, re, json
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "MAGNET_URL": "MAGNIT",
                   "NOTIFY_IDS": "1", "START_PIC": "PIC_START", "CARD_MK": "PIC_MK", "CARD_GUIDE": "PIC_G",
                   "COURSES_ON": "1", "COURSE_BUNDLE_ONLY": "1", "COURSE_PRICES": "3200,1900,3300",
                   "PAY_URL": "https://pay.test/jar", "KABINET_URL": "https://kab.test",
                   "CHANNEL_URL": "https://t.me/kanal"})
os.environ.pop("DATABASE_URL", None)
import requests
V = []
class _R:
    def __init__(s, j): s._j = j
    def json(s): return s._j
def fake_post(url, json=None, data=None, files=None, timeout=None):
    V.append((url.rsplit("/", 1)[-1], json or data or {}))
    return _R({"ok": True, "result": {"message_id": len(V)}})
requests.post = fake_post
import store, bot
KV = {}
store.kv_get = lambda k, d=None: KV.get(k, d)
store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
app = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    if not cond:
        print("  ПАДІННЯ  " + name + (": " + str(extra)[:200] if extra else "")); bad.append(name)

class P:
    def __init__(s, uid):
        s.uid = uid
    def _grab(s):
        out = [p for m, p in V if m in ("sendMessage", "sendPhoto", "sendDocument", "sendVideo") and p.get("chat_id") == s.uid]
        res = []
        for p in out:
            rm = p.get("reply_markup")
            rm = json.loads(rm) if isinstance(rm, str) and rm else (rm or {})
            b = [x for r in rm.get("inline_keyboard", []) for x in r]
            res.append({"text": p.get("text") or p.get("caption") or "", "btns": b, "raw": p})
        return res
    def say(s, text):
        V.clear()
        app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": s.uid},
                 "from": {"id": s.uid, "first_name": "Т"}, "text": text}})
        return s._grab()
    def tap(s, data):
        V.clear()
        app.post("/sekret", json={"callback_query": {"id": "c", "data": data, "from": {"id": s.uid, "first_name": "Т"},
                 "message": {"message_id": 1, "chat": {"id": s.uid}}}})
        return s._grab()

LIGHT = re.compile(r"світл|студійне|гайд|схем", re.I)
LIGHT_CB = {"magnet", "guide", "t1", "t2", "t3"}
def has_light(msgs):
    for m in msgs:
        if LIGHT.search(m["text"]): return m["text"][:60]
        for b in m["btns"]:
            if LIGHT.search(b.get("text", "")) or b.get("callback_data") in LIGHT_CB: return b
    return None
def all_text(msgs):
    return " ".join(m["text"] + " " + " ".join(b.get("text", "") for b in m["btns"]) for m in msgs)
def has_course_card(msgs):
    return any("Курс ретуші, 3300 грн" in m["text"] for m in msgs)
def check_basic(label, msgs):
    ok(label + ": не порожньо", len(msgs) >= 1)
    t = all_text(msgs)
    ok(label + ": без «скоро»", not re.search(r"скоро|незабаром|coming soon", t, re.I), t)
    ok(label + ": українською (без ы э ъ ё)", not re.search(r"[ыэъё]", t), t)
    for m in msgs:
        if "Курс ретуші, 3300 грн" in m["text"]:
            ok(label + ": картка курсу 2970 + -7", "2970 грн" in m["text"] and "-7" in m["text"] and "10 %" in m["text"], m["text"])
            ok(label + ": кнопка оплати на 2970", any("a=2970" in (b.get("url") or "") for b in m["btns"]))

COURSE_TAGS = ("retush", "kurs", "kurs10")
uidn = [1000]
def new():
    uidn[0] += 1
    return P(uidn[0])

def neutral_actions(p, label):
    steps = [("простий /start", lambda: p.say("/start")),
             ("/start ще раз", lambda: p.say("/start")),
             ("/kurs", lambda: p.say("/kurs")),
             ("КУРС", lambda: p.say("КУРС")),
             ("ретуш", lambda: p.say("ретуш")),
             ("Мої матеріали", lambda: p.say("Мої матеріали")),
             ("/moi", lambda: p.say("/moi")),
             ("btn moi", lambda: p.tap("moi")),
             ("btn retush", lambda: p.tap("retush")),
             ("btn k12", lambda: p.tap("k12")),
             ("btn k12z", lambda: p.tap("k12z")),
             ("btn q:new", lambda: p.tap("q:new")),
             ("btn q:pro", lambda: p.tap("q:pro")),
             ("довільний текст", lambda: p.say("Дякую, привіт")),
             ("питання про оплату", lambda: p.say("а як оплатити?")),
             ("я купувала курс", lambda: p.say("я купувала курс")),
             ("btn my:guide", lambda: p.tap("my:guide")),
             ("btn les:k12:1", lambda: p.tap("les:k12:1")),
             ("btn noget:k12z", lambda: p.tap("noget:k12z")),
             ]
    for name, f in steps:
        msgs = f()
        lab = label + " > " + name
        if name != "btn noget:k12z":
            check_basic(lab, msgs)
        w = has_light(msgs)
        ok(lab + ": НЕМА світла", not w, w)

for tag in COURSE_TAGS:
    p = new()
    first = p.say("/start " + tag)
    check_basic(tag + " вхід", first)
    ok(tag + " вхід: нема світла", not has_light(first), has_light(first))
    if tag != "retush":
        ok(tag + " вхід: картка курсу 3300/2970", has_course_card(first), first and first[0]["text"][:80])
    else:
        ok("retush вхід: магніт без ціни", not re.search(r"грн|3300|2970|\$", first[0]["text"]))
    neutral_actions(p, tag + " нова")
    again = p.say("/start " + tag)
    ok(tag + " повторно: нема світла", not has_light(again), has_light(again))
    p2 = P(p.uid)
    r = p2.say("/start")
    ok(tag + " після видалення чату: простий /start нема світла", not has_light(r), has_light(r))
    check_basic(tag + " після видалення", r)

for a, b in (("retush", "kurs"), ("kurs", "retush"), ("retush", "kurs10"), ("kurs10", "retush"), ("kurs", "kurs10")):
    p = new(); p.say("/start " + a); r = p.say("/start " + b)
    ok(a + "->" + b + ": нема світла", not has_light(r), has_light(r))
    r = p.say("/start")
    ok(a + "->" + b + "->/start: нема світла", not has_light(r), has_light(r))
    ok(a + "->" + b + "->/start: повторює " + b, store.kv_get("tag:" + str(p.uid)) == b)
    if b != "retush":
        ok(a + "->" + b + "->/start: картка курсу", has_course_card(r))

p = new(); p.say("/start retush"); r = p.say("/start kurs")
ok("Весь курс з магніту: картка курсу", has_course_card(r) and not has_light(r))
r = p.say("/start")
ok("...і далі простий /start: курс, не світло", has_course_card(r) and not has_light(r))

# світло людина просить сама: має спрацювати
for tag in COURSE_TAGS:
    p = new(); p.say("/start " + tag)
    r = p.say("світло")
    ok(tag + " + слово СВІТЛО: гайд показано", len(r) == 1 and "гайд" in r[0]["text"].lower(), r and r[0]["text"][:60])
    r = p.tap("magnet")
    ok(tag + " + кнопка magnet: щось віддано", len(r) >= 1)

# інші входи
p = new(); r = p.say("/start")
ok("без мітки: магніт світла", len(r) == 1 and any(b.get("callback_data") == "magnet" for b in r[0]["btns"]))
check_basic("без мітки", r)
ok("магніт світла: нема ціни", not re.search(r"грн|\$", r[0]["text"]))
for t in ("inst", "chat"):
    p = new(); r = p.say("/start " + t)
    ok(t + ": магніт світла", any(b.get("callback_data") == "magnet" for b in r[0]["btns"]))
for tag in ("mk", "guide"):
    p = new(); r = p.say("/start " + tag); check_basic(tag, r)
    r2 = p.say("/start"); check_basic(tag + " простий", r2)
    ok(tag + ": простий /start повторює мітку", store.kv_get("tag:" + str(p.uid)) == tag)
p = new(); p.say("/start mk"); r = p.say("/start")
ok("mk -> простий /start: картка МК, не магніт", r and "майстер-клас" in r[0]["text"].lower() and not any(b.get("callback_data") == "magnet" for b in r[0]["btns"]))
p = new(); p.say("/start guide"); r = p.say("/start")
ok("guide -> простий /start: нема магніта", not any(b.get("callback_data") == "magnet" for m in r for b in m["btns"]))

p = new(); r = p.say("/kurs"); ok("/kurs нова: картка курсу 3300/2970", has_course_card(r)); check_basic("/kurs", r)
p = new(); r = p.say("КУРС"); ok("слово КУРС нова: картка курсу", has_course_card(r) and not has_light(r), r and r[0]["text"][:60])
p = new(); r = p.tap("retush"); ok("btn retush нова: картка курсу", has_course_card(r) and not has_light(r))
for w in ("МК", "мк", "майстерклас", "СВІТЛО", "зйомка"):
    p = new(); r = p.say(w); check_basic("слово " + w, r)

# кожна картка курсу з будь-якого кроку: тільки знижкова 2970/3300
p = new()
for d in ("k12", "k12z", "retush", "q:new", "q:pro", "k1", "k2"):
    r = p.tap(d)
    check_basic("callback " + d, r)
    t = all_text(r)
    ok("callback " + d + ": без цін 3200/1900", "3200" not in t and "1900" not in t, t[:120])

# адмін
adm = P(1)
r = adm.say("/start kurs10"); ok("адмін kurs10: картка", has_course_card(r))
r = adm.say("/start"); ok("адмін простий /start після kurs10: курс", has_course_card(r) and not has_light(r))

print("ПАДІННЯ: " + str(len(bad)) + "\n" + "\n".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
