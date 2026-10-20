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
import time as _t
NOW = int(_t.time())
PEND[0]["pick_ts"] = NOW - 20 * 3600          # 501 обрав тариф учора
PEND[1]["pick_ts"] = NOW - 120                # 502 обрав дві хвилини тому
bot.handle_tx({"amount": K * 100, "comment": "", "time": NOW})
ok("двоє на суму, але один обрав тариф щойно: видано йому", GIVEN == [(502, "k12z")], GIVEN)
ok("адміну «за сумою і часом»", any("за сумою і часом" in t for t in admin()), admin())
V.clear(); GIVEN.clear()
PEND[0]["pick_ts"] = NOW - 300; PEND[1]["pick_ts"] = NOW - 120
bot.handle_tx({"amount": K * 100, "comment": "", "time": NOW})
ok("двоє обрали щойно: знову питання адміну", GIVEN == [] and any("/vydaty" in t for t in admin()), admin())
V.clear()
# нічия оплата: двоє обрали щойно, 502 тисне «оплатила»
KV = {}
store.kv_get = lambda k, default=None: KV.get(k, default)
store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
store.kv_claim = lambda k: KV.setdefault("claim:" + k, 0) == 0 and not KV.__setitem__("claim:" + k, 1)
bot.handle_tx({"amount": K * 100, "comment": "", "time": NOW, "id": "tx9"})
ok("нічия оплата записана", "502" in KV.get("tx_nechyia", "") and "501" in KV.get("tx_nechyia", ""), KV)
ok("«оплатила» від 503 (не кандидат): нічого", bot.claim_nechyia(503, "k12z") is False and GIVEN == [], GIVEN)
ok("«оплатила» від 502: видано", bot.claim_nechyia(502, "k12z") is True and GIVEN == [(502, "k12z")], GIVEN)
ok("адміну «за сумою і кнопкою»", any("кнопкою" in t for t in admin()), admin())
ok("«оплатила» від 501 після того: нічого, запис забрано", bot.claim_nechyia(501, "k12z") is False and GIVEN == [(502, "k12z")], GIVEN)
V.clear(); GIVEN.clear()
bot.handle_tx({"amount": 123400, "comment": "від мами", "time": 0})
ok("чужа сума: тиша", GIVEN == [] and admin() == [], admin())
bot.handle_tx({"amount": bot.PRODUCTS["k1"]["uah"] * 100, "comment": "", "time": 0})
ok("ціна товару без тарифу: БЕЗ КОДУ адміну", any("БЕЗ КОДУ" in t for t in admin()), admin())
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
