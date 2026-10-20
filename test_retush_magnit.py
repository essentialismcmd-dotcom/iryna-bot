#!/usr/bin/env python3
"""Лід-магніт ретуші 08.10: /start retush БЕЗ мережі і бази.
Перший екран дослівно з MAGNIT-RETUSH-2026-10-08.md, без ціни і без гайда,
кнопка «Відкрити урок» веде в кабінет на частину 1.3 (20.10: маски замість чистки шкіри)."""
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
import requests
V = []
class _R:
    def __init__(s, j): s._j = j
    def json(s): return s._j
def fake_post(url, json=None, data=None, files=None, timeout=None):
    V.append((url.rsplit("/", 1)[-1], json or data or {}))
    return _R({"ok": True, "result": {"message_id": len(V)}})
requests.post = fake_post
os.environ["FREE_LESSON"] = "1"   # 19.10: магніт уроку вимкнено за замовчуванням, тут перевіряємо його самого
import bot
app = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
USER = {"id": 777, "first_name": "Тест", "username": "t"}
app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": 777}, "from": USER, "text": "/start retush"}})
to_user = [p for m, p in V if p.get("chat_id") == 777 and m in ("sendMessage", "sendPhoto")]
ok("людині пішло одне повідомлення", len(to_user) == 1, len(to_user))
p = to_user[0]
text = p.get("text") or p.get("caption") or ""
ok("текст дослівно", text == bot.RETUSH_MAGNET_HELLO and text.startswith("Привіт, це Ірина Руль ♥️")
   and "«Маски: волосся і фон»" in text and "7 хвилин" in text)
ok("без ціни і гайда", not any(w in text.lower() for w in ("грн", "3300", "3 300", "гайд, ", "$")))
rm = p["reply_markup"]
rm = __import__("json").loads(rm) if isinstance(rm, str) else rm
btns = [b for r in rm["inline_keyboard"] for b in r]
ok("кнопка «Відкрити урок» = Mini App на 1.3", btns[0] == {"text": "Відкрити урок", "web_app": {"url": "https://kab.test/?p=1.3"}}, btns)
ok("магніта світла нема в кнопках", not any("світла" in b["text"] for b in btns))
ok("повідомлення «Урок ваш» ще не йде", True)
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
