#!/usr/bin/env python3
"""19.10: оплата за посиланням на картку Іри приходить без коду. Одна людина з тарифом на цю суму
за добу = її оплата, курс видається сам; кілька людей = питання адміну; чужі суми = тиша."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "COURSES_ON": "1",
                   "PAY_URL": "https://send.monobank.ua/test", "NOTIFY_IDS": "1"})
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
PEND = []
store.pending_by_amount = lambda uah, hours=24: [r for r in PEND if r["amount_uah"] == uah]
store.get_user = lambda uid: {"first_name": "Л" + str(uid)}
PAID = []
store.mark_paid = lambda code, uah=None: PAID.append(code)
store.mark_delivered = lambda code: None
store.ensure_purchase = lambda *a, **k: None
GIVEN = []
bot.deliver = lambda uid, key: GIVEN.append((uid, key)) or True
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
def admin():
    return [p.get("text", "") for m, p in V if p.get("chat_id") == 1]
K = bot.PRODUCTS["k12z"]["uah"]
PEND.append({"user_id": 501, "tier": "k12z", "order_code": bot.order_code(501, "k12z"), "amount_uah": K})
bot.handle_tx({"amount": K * 100, "comment": "Переказ власних коштів", "description": "Анна", "time": 0})
ok("одна людина на цю суму: курс видано", GIVEN == [(501, "k12z")], GIVEN)
ok("адміну «впізнано за сумою»", any("за сумою" in t for t in admin()), admin())
V.clear(); GIVEN.clear()
PEND.append({"user_id": 502, "tier": "k12z", "order_code": bot.order_code(502, "k12z"), "amount_uah": K})
bot.handle_tx({"amount": K * 100, "comment": "", "time": 0})
ok("дві людини на суму: нічого не видано", GIVEN == [], GIVEN)
ok("адміну обидва імені і /vydaty", any("Л501" in t and "Л502" in t and "/vydaty" in t for t in admin()), admin())
V.clear()
bot.handle_tx({"amount": 123400, "comment": "від мами", "time": 0})
ok("чужа сума: тиша", GIVEN == [] and admin() == [], admin())
bot.handle_tx({"amount": bot.PRODUCTS["k1"]["uah"] * 100, "comment": "", "time": 0})
ok("ціна товару без тарифу: БЕЗ КОДУ адміну", any("БЕЗ КОДУ" in t for t in admin()), admin())
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
