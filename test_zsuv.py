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
# 25.10: хто обрав ту саму суму за PICK_WIN після іншого, платить на гривню менше; «оплатила» до банку
import json
K = bot.PRODUCTS["k12z"]["uah"]
ROWS = []
store.pending_amounts = lambda lo, hi, s: [r for r in ROWS if lo <= r["amount_uah"] <= hi]
bot.osobysta_tsina = lambda uid, key, grace=0: K if key in ("k12", "k12z") else None
ok("перший платить рівно", bot.suma_oplaty(601, "k12z", K) == K)
ROWS.append({"user_id": 601, "order_code": bot.order_code(601, "k12z"), "amount_uah": K})
ok("другий на гривню менше", bot.suma_oplaty(602, "k12z", K) == K - 1)
ROWS.append({"user_id": 602, "order_code": bot.order_code(602, "k12z"), "amount_uah": K - 1})
ok("третій на дві", bot.suma_oplaty(603, "k12z", K) == K - 2)
ok("повторний вибір лишає свою суму", bot.suma_oplaty(602, "k12z", K) == K - 1)
store.get_purchase = lambda code: {"status": "new", "amount_uah": K - 1} if code == bot.order_code(602, "k12z") else None
ok("посилання з сумою людини", "a=" + str(K - 1) in bot.pay_url(602, "k12z"), bot.pay_url(602, "k12z"))
ok("чужому посилання з повною", "a=" + str(K) in bot.pay_url(601, "k12z"))
# оплата на K-1 іде лише 602
PEND.clear(); GIVEN.clear(); V.clear()
PEND += [{"user_id": 601, "tier": "k12z", "order_code": bot.order_code(601, "k12z"), "amount_uah": K},
         {"user_id": 602, "tier": "k12z", "order_code": bot.order_code(602, "k12z"), "amount_uah": K - 1}]
bot.handle_tx({"amount": (K - 1) * 100, "comment": "", "time": 0})
ok("оплата K-1 видана другому", GIVEN == [(602, "k12z")], GIVEN)
# Юлія: двоє на одну суму, одна вже тиснула «оплатила»
KV = {}
store.kv_get = lambda k, default=None: KV.get(k, default)
store.kv_set = lambda k, v: KV.__setitem__(k, v)
store.kv_del = lambda k: KV.pop(k, None)
store.kv_claim = lambda k: KV.setdefault(k, "1") == "1" and not KV.__setitem__(k, "2")
PEND.clear(); GIVEN.clear()
PEND += [{"user_id": 701, "tier": "k12z", "order_code": bot.order_code(701, "k12z"), "amount_uah": K},
         {"user_id": 702, "tier": "k12z", "order_code": bot.order_code(702, "k12z"), "amount_uah": K}]
KV["noget_wait:702:k12z"] = "0|x"
import time as _t
bot.handle_tx({"amount": K * 100, "comment": "", "time": int(_t.time()), "id": "tx1"})
ok("«оплатила» до банку: видано їй", GIVEN == [(702, "k12z")], GIVEN)
ok("черга знята", "noget_wait:702:k12z" not in KV)
sys.exit(1 if bad else 0)
