#!/usr/bin/env python3
"""Підсумок продажів Ірі (22.10): рядок «Сьогодні» після оплати лише Ірі, вечірній підсумок о 21:00 Київ."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update(BOT_TOKEN="test:token", WEBHOOK_SECRET="sekret", ADMIN_ID="1", NO_THREADS="1",
                  TEST_MODE="1", COURSES_ON="1", NOTIFY_IDS="1", IRA_ID="2", PAY_URL="https://send.monobank.ua/jar/test",
                  GUIDE_FILE_ID="GUIDE")
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
from datetime import datetime, timezone
import bot

MSG = "send" + "Message"
bad = 0
def check(name, cond):
    global bad
    print(("ok   " if cond else "FAIL ") + name)
    bad += not cond

ROWS = [{"product": "guide", "today_n": 2, "today_uah": 598, "all_n": 9, "all_uah": 2691},
        {"product": "course", "today_n": 1, "today_uah": 2970, "all_n": 5, "all_uah": 14110}]
bot.store.sales_summary = lambda skip: ROWS
check("рядок дня", bot.ira_today_line() == "Сьогодні: гайд 2, курс 1 · 3 568 грн")
check("вечірній текст", bot.pidsumok_text() == "Підсумок дня: гайд 2, курс 1 · 3 568 грн\nЗа весь час: гайд 9, курс 5 · 16 801 грн")
bot.store.sales_summary = lambda skip: [{"product": "guide", "today_n": 0, "today_uah": 0, "all_n": 9, "all_uah": 2691}]
check("без продажів за день: нічого", bot.ira_today_line() is None and bot.pidsumok_text() is None)
bot.store.sales_summary = lambda skip: None
check("без бази: нічого", bot.ira_today_line() is None)

# вечірній запуск: до 21:00 ні, після 21:00 раз (kv_claim)
bot.store.sales_summary = lambda skip: ROWS
claims = []
def claim(k):
    new = k not in claims
    claims.append(k)
    return new
bot.store.kv_claim = claim
CALLS.clear()
check("о 20:59 Київ не шлемо", bot.pidsumok_run(datetime(2026, 10, 22, 17, 59, tzinfo=timezone.utc)) is False and not CALLS)
check("о 21:05 Київ шлемо", bot.pidsumok_run(datetime(2026, 10, 22, 18, 5, tzinfo=timezone.utc)) is True)
ids = sorted(int(p["chat_id"]) for m, p in CALLS if m == MSG)
check("отримали адмін 1 і Іра 2", ids == [1, 2] and "За весь час" in CALLS[0][1]["text"])
CALLS.clear()
check("другий раз того ж дня ні", bot.pidsumok_run(datetime(2026, 10, 22, 18, 15, tzinfo=timezone.utc)) is False and not CALLS)
check("ключ kv з датою Києва", claims[0] == "pidsumok:2026-10-22")

# після оплати: сповіщення всім, рядок «Сьогодні» лише Ірі
bot.store.ensure_purchase = lambda *a, **k: None
bot.store.mark_paid = lambda *a, **k: None
bot.store.mark_delivered = lambda *a, **k: None
bot.store.log_event = lambda *a, **k: None
bot.deliver = lambda uid, key: True
bot.kabinet_mist.push_user = lambda uid: None
CALLS.clear()
bot._pay_issue(555, "t1", "IRTEST-1", bot.PRODUCTS["t1"]["uah"] * 100)
msgs = [(int(p["chat_id"]), p["text"]) for m, p in CALLS if m == MSG]
check("оплата: адмін і Іра отримали «Оплата …»", sorted(c for c, t in msgs if t.startswith("Оплата ") and "видано" in t) == [1, 2])
check("рядок «Сьогодні» лише Ірі", [c for c, t in msgs if t.startswith("Сьогодні:")] == [2])
# /prodazh (23.10): ручна видача як продаж з картки, kv prodazh:<код> = сума
KV = {}
bot.store.kv_set = lambda k, v: KV.__setitem__(k, v)
bot.store.get_purchase = lambda code: {"order_code": code} if code.endswith("-" + bot.PRODUCTS["k12"]["code"]) else None
ENS = []
bot.store.ensure_purchase = lambda *a, **k: ENS.append(k)
code, msg = bot.prodazh_mark(897646290, 2500)
check("курс: код k12 і kv", code == bot.order_code(897646290, "k12") and KV.get("prodazh:" + code) == "2500")
check("рядок був: без ensure", not ENS and msg.startswith("Зараховано: ") and "2500 грн" in msg)
code2, _ = bot.prodazh_mark(1164433116, 299, "gaid")
check("гайд: код t1, рядка не було: ensure з сумою", code2.endswith("-" + bot.PRODUCTS["t1"]["code"]) and ENS and ENS[-1]["amount_uah"] == 299)
c = bot.app.test_client()
r = c.post("/prodazh/sekret", data={"id": "1164433116", "uah": "2970", "key": "k12", "by": "test"})
check("маршрут /prodazh", r.status_code == 200 and r.get_json()["ok"] and KV.get("prodazh:" + bot.order_code(1164433116, "k12")) == "2970")
r = c.post("/prodazh/sekret", data={"id": "x", "uah": "1"})
check("маршрут: погані поля 400", r.status_code == 400)
sys.exit(1 if bad else 0)
