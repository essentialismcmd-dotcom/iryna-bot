#!/usr/bin/env python3
"""POST /kabinet-kupyty (08.10) БЕЗ мережі і бази: ключ, картка k12z, мітка retush."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1", "COURSES_ON": "1",
                   "PAY_URL": "https://send.monobank.ua/jar/test", "NOTIFY_IDS": "1",
                   "KABINET_URL": "https://kab.test/", "KABINET_KEY": "test-key", "COURSE_BUNDLE_ONLY": "1"})
os.environ.pop("DATABASE_URL", None)
import requests
V = []
class _R:
    def __init__(s, j): s._j = j; s.status_code = 200
    def json(s): return s._j
def fake_post(url, json=None, data=None, files=None, timeout=None, headers=None):
    V.append((url.rsplit("/", 1)[-1], json or data or {}))
    return _R({"ok": True, "result": {"message_id": len(V)}})
requests.post = fake_post
import bot, store
KV = {}
store.kv_get = lambda k, d=None: KV.get(k, d)
store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
c = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
H = {"X-Kabinet-Key": "test-key"}
def cards(uid): return [p for m, p in V if p.get("chat_id") == uid and m in ("sendMessage", "sendPhoto")]
ok("без ключа 403", c.post("/kabinet-kupyty", json={"user_id": 777}).status_code == 403)
ok("чужий ключ 403", c.post("/kabinet-kupyty", json={"user_id": 777}, headers={"X-Kabinet-Key": "x"}).status_code == 403)
ok("жодної картки без ключа", not cards(777))
ok("без user_id 400", c.post("/kabinet-kupyty", json={}, headers=H).status_code == 400)
r = c.post("/kabinet-kupyty", json={"user_id": 777}, headers=H)
ok("з ключем 200", r.status_code == 200, r.status_code)
cs = cards(777)
ok("людині пішла одна картка", len(cs) == 1, len(cs))
t = cs[0].get("text") or cs[0].get("caption") or ""
ok("це k12z (знижкова)", bot.PRODUCTS["k12z"]["text"] in t, t[:80])
ok("мітка retush", store.kv_get("tag:777") == "retush")
ok("адміну картка теж", c.post("/kabinet-kupyty", json={"user_id": 1}, headers=H).status_code == 200 and len(cards(1)) >= 1)
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
