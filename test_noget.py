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

# 1. натиснула кнопку: текст про банк, адміну нічого, у черзі ключ
CALLS.clear()
bot.noget_wait(555, "t1", "Тест, @test, id 555")
bot.send(555, bot.NOGET_TEXT)
check("людині текст про банк", any("Банк передає оплату" in t for t in texts(555)))
check("адміну поки нічого", not texts(1))
check("ключ у черзі", "noget_wait:555:t1" in KV)

# 2. рано: за 5 хв нічого
CALLS.clear()
ts = float(KV["noget_wait:555:t1"].split("|")[0])
check("через 5 хв ще чекаємо", bot.noget_run(ts + 300) == 0 and not texts(1) and "noget_wait:555:t1" in KV)

# 3. оплата дійшла: мовчки знімаємо
PURCH[bot.order_code(555, "t1")] = {"status": "delivered"}
check("оплата дійшла: адміну нічого, ключ знято", bot.noget_run(ts + 700) == 0 and not texts(1) and "noget_wait:555:t1" not in KV)

# 4. оплата не дійшла: після паузи адміну «КАЖЕ, ЩО ОПЛАТИВ» з кнопкою видачі
PURCH.clear(); KV.clear(); CALLS.clear()
bot.noget_wait(777, "t1", "Друга, id 777")
ts = float(KV["noget_wait:777:t1"].split("|")[0])
n = bot.noget_run(ts + 700)
adm = [p for m, p in CALLS if m == MSG and int(p["chat_id"]) == 1]
check("через 10+ хв адміну повідомлення", n == 1 and adm and adm[0]["text"].startswith("КАЖЕ, ЩО ОПЛАТИВ") and "Друга, id 777" in adm[0]["text"])
check("кнопка «Видати вручну»", adm and "give:777:t1" in str(adm[0].get("reply_markup")))
check("ключ знято", "noget_wait:777:t1" not in KV)
CALLS.clear()
check("повтор черги нічого не шле", bot.noget_run(ts + 1400) == 0 and not texts(1))

# 5. без бази (kv не тримає): адміну одразу
bot.store.kv_get = lambda k, default=None: default
bot.store.kv_set = lambda k, v: None
CALLS.clear()
bot.noget_wait(888, "t1", "Третя, id 888")
check("без бази адміну одразу", any(t.startswith("КАЖЕ, ЩО ОПЛАТИВ") for t in texts(1)))
sys.exit(1 if bad else 0)
