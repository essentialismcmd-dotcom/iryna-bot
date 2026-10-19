#!/usr/bin/env python3
"""19.10, слово Yaro: урок 1.5 не роздаємо. /start retush без FREE_LESSON одразу дає картку курсу
з кодом і оплатою, без «Відкрити урок»."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1", "COURSES_ON": "1",
                   "PAY_URL": "https://send.monobank.ua/jar/test", "NOTIFY_IDS": "1",
                   "KABINET_URL": "https://kab.test/"})
os.environ.pop("DATABASE_URL", None)
os.environ.pop("KABINET_KEY", None)
os.environ.pop("FREE_LESSON", None)
import requests
V = []
class _R:
    def __init__(s, j): s._j = j
    def json(s): return s._j
def fake_post(url, json=None, data=None, files=None, timeout=None):
    V.append((url.rsplit("/", 1)[-1], json or data or {}))
    return _R({"ok": True, "result": {"message_id": len(V)}})
requests.post = fake_post
import bot
app = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
USER = {"id": 777, "first_name": "Тест", "username": "t"}
ok("FREE_LESSON вимкнено за замовчуванням", bot.FREE_LESSON is False)
app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": 777}, "from": USER, "text": "/start retush"}})
to_user = [p for m, p in V if p.get("chat_id") == 777 and m in ("sendMessage", "sendPhoto")]
ok("людині пішло одне повідомлення", len(to_user) == 1, len(to_user))
p = to_user[0]
text = p.get("text") or p.get("caption") or ""
ok("це картка курсу, без «впишіть»", "курс" in text.lower() and "Призначення платежу" not in text, text[:80])
ok("про урок 1.5 ні слова", "Відкрити урок" not in text and "Чистка шкіри" not in text)
rm = p["reply_markup"]
rm = __import__("json").loads(rm) if isinstance(rm, str) else rm
btns = [b for r in rm["inline_keyboard"] for b in r]
ok("кнопки «Відкрити урок» нема", not any(b["text"] == "Відкрити урок" for b in btns), btns)
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
