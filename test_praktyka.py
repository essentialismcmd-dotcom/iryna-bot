#!/usr/bin/env python3
"""Кнопка кабінету «Отримати в Telegram»: практика без відео, лише покупцям, без мережі і бази."""
import os, sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update(BOT_TOKEN="test:token", WEBHOOK_SECRET="sekret", ADMIN_ID="1", NO_THREADS="1",
                  TEST_MODE="1", COURSES_ON="1", NOTIFY_IDS="1", KABINET_URL="http://x", KABINET_KEY="kk",
                  COURSE1_FILES="Урок 1 · основи. Практика > video:V1, document:RAF1, document:PSD1 | Урок 2 · бʼюті. Практика > document:RAF2, document:PSD2 | Урок 3 · бʼюті. Практика > document:RAF3",
                  COURSE2_FILES="Практика · набір 1 > document:R21 | Практика · набір 2 > document:A2, document:B2 | Практика · набір 6 > document:A6")
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
check("k1: три розділи, відео V1 не потрапило", [[f for _, f in d] for _, d in items] == [["RAF1", "PSD1"], ["RAF2", "PSD2"], ["RAF3"]])
check("k2 лише коли куплений", [t for t, _ in bot.practice_items({"k1", "k2"})][-1] == "Практика · набір 6")
check("без курсу порожньо", bot.practice_items(set()) == [])

bot.owned_keys = lambda uid: set()
check("не покупець: нічого не шлемо", bot.send_practice(5) is None and not CALLS)
bot.owned_keys = lambda uid: {"k1"}
bot.store.log_event = lambda *a, **k: None
check("покупець: пішло 5 файлів", bot.send_practice(5) == 5)
check("перше повідомлення одразу, з числом", CALLS[0][0] == "sendMessage" and "5 файлів" in CALLS[0][1]["text"])
check("заголовок як підпис альбому, не окремим повідомленням", sum(m == "sendMessage" for m, _ in CALLS) == 1 and [p.get("media", [{}])[0].get("caption") for m, p in CALLS if m == "sendMediaGroup"] == ["Урок 1 · основи. Практика", "Урок 2 · бʼюті. Практика"])
check("відео не слали", not any(m == "sendVideo" for m, _ in CALLS))

# блоки (11.10): кожна кнопка шле лише свої файли
def sent_ids(calls):
    out = []
    for m, p in calls:
        if m == "sendMediaGroup":
            out += [x["media"] for x in p["media"]]
        elif m == "sendDocument":
            out.append(p["document"])
    return out
bot.owned_keys = lambda uid: {"k1", "k2"}
def run(block):
    CALLS.clear()
    n = bot.send_practice(5, block)
    return n, sent_ids(CALLS), [p.get("media", [{}])[0].get("caption") or p.get("caption") for m, p in CALLS if m != "sendMessage"]
check("u1: лише RAF1, PSD1", run("u1")[:2] == (2, ["RAF1", "PSD1"]))
n, ids, caps = run("u2")
check("u2: урок 2 і набір 1 (колір 2121001.raf)", sorted(ids) == ["PSD2", "R21", "RAF2"] and n == 3 and caps[0].startswith("Файли до уроку 2"))
check("u3: лише RAF3", run("u3")[:2] == (1, ["RAF3"]))
check("c1: набір 2", run("c1")[:2] == (2, ["A2", "B2"]))
check("c5: набір 6", run("c5")[:2] == (1, ["A6"]))
check("c3: файлів нема, нічого не шлемо", run("c3")[0] is None and not CALLS)
bot.owned_keys = lambda uid: {"k1"}
check("c1 без k2: нічого", run("c1")[0] is None and not CALLS)
check("u1 з k1 тільки: не шле u2", "PSD2" not in run("u1")[1])
bot.owned_keys = lambda uid: {"k1"}

c = bot.app.test_client()
check("блок з ключем: 200", c.post("/kabinet-praktyka", json={"user_id": 5, "block": "u1"}, headers={"X-Kabinet-Key": "kk"}).status_code == 200)
check("поганий блок 400", c.post("/kabinet-praktyka", json={"user_id": 5, "block": "zzz"}, headers={"X-Kabinet-Key": "kk"}).status_code == 400)
check("без ключа 403", c.post("/kabinet-praktyka", json={"user_id": 5}).status_code == 403)
check("поганий ключ 403", c.post("/kabinet-praktyka", json={"user_id": 5}, headers={"X-Kabinet-Key": "no"}).status_code == 403)
check("без user_id 400", c.post("/kabinet-praktyka", json={}, headers={"X-Kabinet-Key": "kk"}).status_code == 400)
sys.exit(1 if bad else 0)
