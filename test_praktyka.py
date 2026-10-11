#!/usr/bin/env python3
"""Кнопка кабінету «Отримати в Telegram»: практика без відео, лише покупцям, без мережі і бази."""
import os, sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update(BOT_TOKEN="test:token", WEBHOOK_SECRET="sekret", ADMIN_ID="1", NO_THREADS="1",
                  TEST_MODE="1", COURSES_ON="1", NOTIFY_IDS="1", KABINET_URL="http://x", KABINET_KEY="kk",
                  COURSE1_FILES="Урок 1 > video:V1, document:RAF1, document:PSD1 | Урок 2 > document:RAF2, document:PSD2",
                  COURSE2_FILES="Колір > document:RAF3, document:PSD3")
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
import time; time.sleep = lambda *_: None
import bot

bad = 0
def check(name, cond):
    global bad
    print(("ok   " if cond else "FAIL ") + name)
    bad += not cond

items = bot.practice_items({"k1"})
check("k1: два розділи, відео V1 не потрапило", [[f for _, f in d] for _, d in items] == [["RAF1", "PSD1"], ["RAF2", "PSD2"]])
check("k2 лише коли куплений", [t for t, _ in bot.practice_items({"k1", "k2"})][-1] == "Колір")
check("без курсу порожньо", bot.practice_items(set()) == [])

bot.owned_keys = lambda uid: set()
check("не покупець: нічого не шлемо", bot.send_practice(5) is None and not CALLS)
bot.owned_keys = lambda uid: {"k1"}
bot.store.log_event = lambda *a, **k: None
check("покупець: пішло 4 файли", bot.send_practice(5) == 4)
check("перше повідомлення одразу, з числом", CALLS[0][0] == "sendMessage" and "4 файлів" in CALLS[0][1]["text"])
check("заголовок як підпис альбому, не окремим повідомленням", sum(m == "sendMessage" for m, _ in CALLS) == 1 and [p.get("media", [{}])[0].get("caption") for m, p in CALLS if m == "sendMediaGroup"] == ["Урок 1", "Урок 2"])
check("відео не слали", not any(m == "sendVideo" for m, _ in CALLS))

c = bot.app.test_client()
check("без ключа 403", c.post("/kabinet-praktyka", json={"user_id": 5}).status_code == 403)
check("поганий ключ 403", c.post("/kabinet-praktyka", json={"user_id": 5}, headers={"X-Kabinet-Key": "no"}).status_code == 403)
check("без user_id 400", c.post("/kabinet-praktyka", json={}, headers={"X-Kabinet-Key": "kk"}).status_code == 400)
sys.exit(1 if bad else 0)
