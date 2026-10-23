#!/usr/bin/env python3
"""22.10: людина з пресетом тисне «Забрати три схеми світла» → схеми, а не «Пресет уже у вас»."""
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
    CALLS.append((url.rsplit("/", 1)[-1], json or data or {}))
    return _R({"ok": True, "result": {"message_id": 1}})
requests.post = fake_post
time.sleep = lambda *_: None
import bot

MSG = "send" + "Message"
bad = 0
def check(name, cond):
    global bad
    print(("ok   " if cond else "FAIL ") + name)
    bad += not cond
def texts(chat):
    return [p["text"] for m, p in CALLS if m == MSG and int(p["chat_id"]) == chat]

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
PRESETS = []
bot.give_preset = lambda chat_id, keys=None: PRESETS.append(chat_id)

U = {"id": 555, "first_name": "Alena"}
# 1. прийшла по пресет, «Я підписалась»: пресет
KV["preset_wait:555"] = "1"
bot.sub_check(555, 555, U)
check("перший раз пресет", PRESETS == [555] and not GIFTS)
check("мітка preset_wait знята", "preset_wait:555" not in KV)
# 2. тисне «Забрати три схеми»: схеми, не «Пресет уже у вас»
CALLS.clear()
bot.sub_check(555, 555, U)
check("другий раз схеми", GIFTS == [555] and PRESETS == [555])
check("без «Пресет уже у вас»", not any("Пресет уже у вас" in t for t in texts(555)))
# 3. стара людина: пресет виданий раніше, мітка лишилась (як Alena до правки)
KV.clear(); GIFTS.clear(); PRESETS.clear(); CALLS.clear()
KV["preset_wait:777"] = "1"; KV["preset_given:777"] = "1"
bot.sub_check(777, 777, {"id": 777, "first_name": "Стара"})
check("стара мітка: схеми одразу", GIFTS == [777] and not PRESETS and "preset_wait:777" not in KV)
sys.exit(1 if bad else 0)
