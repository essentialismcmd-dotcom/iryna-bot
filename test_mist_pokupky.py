#!/usr/bin/env python3
"""29.10, слово Yaro: асистентка знає, хто що купив. /mist/<key>/pokupky віддає ключі продуктів, дату, нік;
без сум; персонал не віддає; без ключа 404. Без бази: підставний store.q."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1", "NOTIFY_IDS": "1", "MIST_KEY": "kliuch"})
os.environ.pop("DATABASE_URL", None)
import bot, store
ROWS = [
    {"user_id": 891005959, "tier": "k12z", "product": "course", "t": "2026-10-29 12:00:00+00", "username": "ph_Ruslana", "first_name": "Руслана", "last_name": None, "got_magnet_at": "2026-10-18"},
    {"user_id": 6777702465, "tier": "t2", "product": "guide", "t": "2026-10-28 20:00:00+00", "username": "yaroslavkopchyk", "first_name": "YR", "last_name": None, "got_magnet_at": None},
    {"user_id": 1, "tier": "k12", "product": "course", "t": "2026-10-01 10:00:00+00", "username": "y", "first_name": "Yaro", "last_name": None, "got_magnet_at": None},
]
def fake_q(sql, args=(), fetch=None):
    rows = ROWS
    if args:
        rows = [r for r in rows if r["user_id"] == args[0]]
    return rows
store.q = fake_q
store.session_begin = lambda: None
store.session_end = lambda: None
app = bot.app.test_client()
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
ok("чужий ключ 404", app.get("/mist/zlyi/pokupky").status_code == 404)
d = app.get("/mist/kliuch/pokupky").get_json()
l = {x["uid"]: x for x in d["liudy"]}
ok("персонал (admin 1) не віддаємо", 1 not in l, list(l))
ok("Руслана k12z → k1 і k2", [x["shcho"] for x in l[891005959]["kupyv"]] == ["k1", "k2"], l.get(891005959))
ok("YR t2 → t1, дата", l[6777702465]["kupyv"] == [{"shcho": "t1", "koly": "2026-10-28 20:00"}], l.get(6777702465))
ok("магніт у Руслани, нік, ім'я", l[891005959]["mahnit"] and l[891005959]["nik"] == "ph_Ruslana" and l[891005959]["imia"] == "Руслана")
ok("сум нема у відповіді", "amount" not in str(d) and "uah" not in str(d))
one = app.get("/mist/kliuch/pokupky?uid=6777702465").get_json()["liudy"]
ok("?uid= одна людина", [x["uid"] for x in one] == [6777702465], one)
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
