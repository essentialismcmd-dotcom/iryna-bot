#!/usr/bin/env python3
"""22.10: мітка shema4 (схема 4 «циклорама» з опитування каналу): файл після «Я підписалась» раз назавжди,
другий натиск веде до трьох схем; людина з пресетом і схемою 4 не плутається."""
import os, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update(BOT_TOKEN="test:token", WEBHOOK_SECRET="sekret", ADMIN_ID="1", NO_THREADS="1",
                  TEST_MODE="1", COURSES_ON="1", NOTIFY_IDS="1", IRA_ID="2", GIFT_FOR_SUB="1",
                  PAY_URL="https://send.monobank.ua/jar/test", GUIDE_FILE_ID="GUIDE")
os.environ.pop("DATABASE_URL", None)
import requests
CALLS = []
class _R:
    def __init__(self, j): self._j = j
    def json(self): return self._j
def fake_post(url, json=None, data=None, files=None, timeout=None):
    CALLS.append((url.rsplit("/", 1)[-1], json or data or {}, files))
    return _R({"ok": True, "result": {"message_id": 1}})
requests.post = fake_post
time.sleep = lambda *_: None
import bot

MSG = "send" + "Message"
DOC = "send" + "Document"
bad = 0
def check(name, cond):
    global bad
    print(("ok   " if cond else "FAIL ") + name)
    bad += not cond
def texts(chat):
    return [p["text"] for m, p, _ in CALLS if m == MSG and int(p["chat_id"]) == chat]
def docs(chat):
    return [(p, f) for m, p, f in CALLS if m == DOC and int(p["chat_id"]) == chat]

KV = {}
bot.store.kv_get = lambda k, default=None: KV.get(k, default)
bot.store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
bot.store.kv_del = lambda k: KV.pop(k, None)
def claim(k):
    if k in KV: return False
    KV[k] = "1"; return True
bot.store.kv_claim = claim
bot.store.log_event = lambda *a, **k: None
bot.kanal_member_fresh = lambda uid: (True, "так")
GIFTS = []
bot.give_gift = lambda uid, text: (GIFTS.append(uid), True)[1]

U = {"id": 555, "first_name": "Тест"}
# 0. файл у репозиторії
path = os.path.join(os.path.dirname(os.path.abspath(bot.__file__)), bot.SHEMA4_FILE)
check("PDF схеми 4 у static", os.path.isfile(path) and os.path.getsize(path) > 100_000)

# 1. прийшла по схему 4, «Я підписалась»: текст, PDF, місток до гайда
KV["shema4_wait:555"] = "1"
bot.sub_check(555, 555, U)
check("дякую + файл нижче", any(t.startswith("Дякую, що ви з нами") for t in texts(555)))
d = docs(555)
check("PDF пішов документом", len(d) == 1 and d[0][1] and "Iryna-Rul-Shema-4-tsyklorama.pdf" in str(d[0][1]))
check("підпис до файла", d and "циклорамою" in d[0][0].get("caption", ""))
check("місток: ще дванадцять у гайді", any("ще дванадцять" in str(p.get("caption", "")) + str(p.get("text", "")) for m, p, _ in CALLS))
check("кнопка гайда є", any("Хочу повний гайд" in str(p.get("reply_markup")) for m, p, _ in CALLS))
check("три схеми не видавали", not GIFTS)
check("мітка shema4_wait знята", "shema4_wait:555" not in KV and KV.get("shema4_given:555") == "1")

# 2. другий натиск «Я підписалась» / «Забрати три схеми»: три схеми, без другого PDF
CALLS.clear()
bot.sub_check(555, 555, U)
check("другий раз три схеми", GIFTS == [555] and not docs(555))

# 3. клавіатура «Канал» + «Я підписалась» для shema4, поки чекає
KV.clear(); KV["shema4_wait:777"] = "1"
kb = bot._sub_kb_for(777)
check("клавіатура з «Я підписалась»", "sub:check" in str(kb))

# 4. старт ?start=shema4 ставить мітку і шле привіт Іри (25.10: людина ще не в каналі, інакше файл одразу)
bot.kanal_member_fresh = lambda uid: (False, "ні")
CALLS.clear(); KV.clear()
SENT = []
bot.send_card = lambda chat_id, pic, text, kb=None, **k: SENT.append((chat_id, text, kb))
bot.bg = lambda fn, *a, **k: None
bot.store.touch_user = lambda u, **k: {"is_new": True}
bot.store.get_user = lambda uid: {}
bot.store.kv_get = lambda k, default=None: KV.get(k, default)
upd = {"message": {"message_id": 1, "chat": {"id": 888, "type": "private"},
                   "from": {"id": 888, "first_name": "Нова"}, "text": "/start shema4"}}
bot.app.test_client().post("/sekret", json=upd)
check("старт: мітка shema4_wait", KV.get("shema4_wait:888") == "1")
check("старт: привіт про циклораму", any("підсвіченою циклорамою" in t for _, t, _ in SENT))
check("старт: без трьох схем у привіті", not any("Три схеми світла з одного сетапу" in t for _, t, _ in SENT))

# 5. мала пресет-мітку, прийшла по схему 4: останній лінк головний (22.10, 5413676351)
KV.clear(); KV["preset_wait:999"] = "1"
upd["message"]["chat"]["id"] = 999; upd["message"]["from"]["id"] = 999
bot.app.test_client().post("/sekret", json=upd)
check("старт shema4 знімає preset_wait", "preset_wait:999" not in KV and KV.get("shema4_wait:999") == "1")
sys.exit(1 if bad else 0)
