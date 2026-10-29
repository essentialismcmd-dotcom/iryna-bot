#!/usr/bin/env python3
"""Кнопка «оплатив, а файлу немає» (22.10): людині текст про банк, адміну не одразу, а через NOGET_WAIT,
і лише якщо оплата так і не дійшла. Без бази повідомляємо одразу."""
import os, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update(BOT_TOKEN="test:token", WEBHOOK_SECRET="sekret", ADMIN_ID="1", NO_THREADS="1",
                  TEST_MODE="1", COURSES_ON="1", NOTIFY_IDS="1", IRA_ID="2", NOGET_WAIT="600",
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

def texts(chat=None):
    return [p["text"] for m, p in CALLS if m == MSG and (chat is None or int(p["chat_id"]) == chat)]

# штучна kv у пам'яті
KV = {}
bot.store.kv_get = lambda k, default=None: KV.get(k, default)
bot.store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
bot.store.kv_del = lambda k: KV.pop(k, None)
bot.store.kv_prefix = lambda pre: [{"k": k, "v": v} for k, v in KV.items() if k.startswith(pre)]
bot.store.log_event = lambda *a, **k: None
PURCH = {}
bot.store.get_purchase = lambda code: PURCH.get(code)
bot.store.purchases_of = lambda uid, only_paid=True: []

# 1. натиснула кнопку: текст про банк, адміну одразу (25.10 Yaro), у черзі ключ
CALLS.clear()
bot.noget_wait(555, "t1", "Тест, @test, id 555")
bot.send(555, bot.NOGET_TEXT)
check("людині текст про банк і куди писати", any("Перевіряю оплату" in t and "@iryna_rul_studio" in t for t in texts(555)))
check("адміну одразу з кнопкою видачі", any(t.startswith("КАЖЕ, ЩО ОПЛАТИВ") for t in texts(1)) and "give:555:t1" in str(CALLS))
check("ключ у черзі", "noget_wait:555:t1" in KV)

# 2. оплата дійшла: черга знімається мовчки
CALLS.clear()
ts = float(KV["noget_wait:555:t1"].split("|")[0])
PURCH[bot.order_code(555, "t1")] = {"status": "delivered"}
check("оплата дійшла: адміну нічого, ключ знято", bot.noget_run(ts + 700) == 0 and not texts(1) and "noget_wait:555:t1" not in KV)

# 3. оплата не дійшла: повторно адміну не шлемо, ключ знято
PURCH.clear(); KV.clear()
bot.noget_wait(777, "t1", "Друга, id 777")
CALLS.clear()
ts = float(KV["noget_wait:777:t1"].split("|")[0])
check("через 10 хв адміну без дубля, людині «не бачу, напишіть в особисті»",
      bot.noget_run(ts + 700) == 1 and not texts(1) and any("не бачу" in t for t in texts(777)) and "noget_wait:777:t1" not in KV)

# 5. без бази (kv не тримає): адміну одразу
bot.store.kv_get = lambda k, default=None: default
bot.store.kv_set = lambda k, v: None
CALLS.clear()
bot.noget_wait(888, "t1", "Третя, id 888")
check("без бази адміну одразу", any(t.startswith("КАЖЕ, ЩО ОПЛАТИВ") for t in texts(1)))
sys.exit(1 if bad else 0)
