#!/usr/bin/env python3
"""POST /kabinet-podiia (08.10) БЕЗ мережі і бази: ключ, сповіщення персоналу, дедуп."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1", "NOTIFY_IDS": "1,2",
                   "KABINET_URL": "https://kab.test/", "KABINET_KEY": "test-key"})
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
store.get_user = lambda uid: {"username": "loifyanna", "first_name": "Anna"} if uid == 777 else None
c = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
H = {"X-Kabinet-Key": "test-key"}
def msgs(): return [p for m, p in V if m == "sendMessage"]
B = {"user_id": 777, "lesson": "1.5", "kind": "start", "pct": 0}
ok("без ключа 403", c.post("/kabinet-podiia", json=B).status_code == 403)
ok("чужий ключ 403", c.post("/kabinet-podiia", json=B, headers={"X-Kabinet-Key": "x"}).status_code == 403)
ok("нічого не надіслано без ключа", not msgs())
ok("без user_id 400", c.post("/kabinet-podiia", json={"kind": "start"}, headers=H).status_code == 400)
ok("чужа подія 400", c.post("/kabinet-podiia", json={**B, "kind": "hack"}, headers=H).status_code == 400)
ok("start 200", c.post("/kabinet-podiia", json=B, headers=H).status_code == 200)
m = msgs()
ok("двом із NOTIFY_IDS", sorted(p["chat_id"] for p in m) == [1, 2], m)
ok("текст start", m and m[0]["text"] == "Anna (@loifyanna, id 777) почала урок 1.5", m and m[0]["text"])
n = len(m)
ok("повтор start: dup, без нових", c.post("/kabinet-podiia", json=B, headers=H).get_data(as_text=True) == "dup" and len(msgs()) == n)
ok("done 200", c.post("/kabinet-podiia", json={**B, "kind": "done", "pct": 95, "min": 12}, headers=H).status_code == 200)
ok("текст done", msgs()[-1]["text"] == "Anna (@loifyanna, id 777) додивилась урок 1.5 (12 хв)", msgs()[-1]["text"])
c.post("/kabinet-podiia", json={**B, "lesson": "1.6"}, headers=H)
ok("інший урок знову шле", len(msgs()) == n + 4)
c.post("/kabinet-podiia", json={**B, "user_id": 5}, headers=H)
ok("невідома людина без юзера: не падає", "без юзернейма" in msgs()[-1]["text"], msgs()[-1]["text"])
bot.kabinet_mist.KEY = ""
ok("без KABINET_KEY мертвий 403 навіть з порожнім ключем", c.post("/kabinet-podiia", json=B, headers={"X-Kabinet-Key": ""}).status_code == 403)
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
