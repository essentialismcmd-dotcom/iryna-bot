#!/usr/bin/env python3
"""19.10, слово Yaro: особиста ціна курсу. /tsina <id> <грн> + текст шле людині картку з кодом k12z
і кнопкою банки на цю суму; оплата цієї суми з кодом видає курс, менша ні."""
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
import bot, store
KV = {}
store.kv_get = lambda k, default=None: KV.get(k, default)
store.kv_set = lambda k, v: KV.__setitem__(k, v)
GIVEN = []
bot.deliver = lambda uid, key: GIVEN.append((uid, key)) or True
app = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
ADMIN = {"id": 1, "first_name": "Yaro", "username": "y"}
ANNA = 897646290
app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": 1}, "from": ADMIN,
                                      "text": "/tsina " + str(ANNA) + " 2500\nАня, тримай ♥️"}})
to_her = [p for m, p in V if p.get("chat_id") == ANNA]
ok("Анні пішла одна картка", len(to_her) == 1, len(to_her))
p = to_her[0]
code = bot.order_code(ANNA, "k12z")
ok("лише текст Yaro, без «впишіть»", p["text"] == "Аня, тримай ♥️", p["text"])
rm = p["reply_markup"]
rm = __import__("json").loads(rm) if isinstance(rm, str) else rm
url = rm["inline_keyboard"][0][0].get("url", "")
ok("банка на 2500 з кодом", "a=2500" in url and "t=" + code in url, url)
to_admin = [p for m, p in V if p.get("chat_id") == 1]
ok("адміну «Надіслано»", any("Надіслано" in (q.get("text") or "") for q in to_admin))
bot.handle_tx({"amount": 200000, "comment": code})
ok("2000 грн: не видано", GIVEN == [], GIVEN)
bot.handle_tx({"amount": 250000, "comment": code})
ok("2500 грн: курс видано", GIVEN == [(ANNA, "k12z")], GIVEN)
ok("іншим ціна звичайна", bot.osobysta_tsina(777, "k12z") is None and "a=" + str(bot.PRODUCTS["k12z"]["uah"]) in bot.pay_url(777, "k12z"))
V.clear()
app.post("/sekret", json={"message": {"message_id": 2, "chat": {"id": 1}, "from": ADMIN, "text": "/tsina 5 2500"}})
ok("без тексту: підказка, людині нічого", not any(p.get("chat_id") == 5 for m, p in V))
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
