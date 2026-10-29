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

# 29.10 «запускай»: навігатор під MIST_KEY (секрет вебхука лише на Render); без ?de=kanal лише чернетка
VYKLYKY = []
_stary_raw = bot.api_raw
def _fake_raw(method, **p):
    VYKLYKY.append((method, p))
    return {"ok": True, "result": {"message_id": 7}}
bot.api_raw = _fake_raw
ok("навігатор: чужий ключ 404", app.post("/mist/zlyi/navihator").status_code == 404 and not VYKLYKY)
r = app.post("/mist/kliuch/navihator")
ok("навігатор: свій ключ публікує в чернетку і закріплює", r.status_code == 200 and VYKLYKY
   and VYKLYKY[0][0].endswith("Message") and VYKLYKY[0][1]["chat_id"] == bot.CHERNETKA
   and VYKLYKY[0][1]["text"] == bot.NAV_TEXT and VYKLYKY[1][0] == "pinChatMessage", str(VYKLYKY[:1])[:200])
ok("навігатор: без ?opys опис не чіпає", not any(m == "setChatDescription" for m, _ in VYKLYKY))
VYKLYKY.clear()
app.post("/mist/kliuch/navihator?de=kanal&opys=1")
ok("навігатор: ?de=kanal&opys=1 у канал з описом", VYKLYKY and VYKLYKY[0][1]["chat_id"] == bot.CHANNEL_ID
   and any(m == "setChatDescription" and p["description"] == bot.NAV_OPYS for m, p in VYKLYKY))
VYKLYKY.clear()
ok("прибрати пост: без mid 400", app.post("/mist/kliuch/vydalyty").status_code == 400 and not VYKLYKY)
ok("прибрати пост: чужий ключ 404", app.post("/mist/zlyi/vydalyty?mid=120").status_code == 404 and not VYKLYKY)
r = app.post("/mist/kliuch/vydalyty?mid=120")
ok("прибрати пост: deleteMessage у каналі", r.status_code == 200 and VYKLYKY == [("deleteMessage", {"chat_id": bot.CHANNEL_ID, "message_id": 120})], str(VYKLYKY))
bot.api_raw = _stary_raw
ok("опис бота: особисті і «сама»", "@iryna_rul_studio" in bot.DESCRIPTIONS[""] and "відповідаю сама" in bot.DESCRIPTIONS[""]
   and len(bot.DESCRIPTIONS[""]) <= 512)
ok("про себе ≤ 120", 0 < len(bot.OPYS_KOROTKO) <= 120 and "@iryna_rul_studio" in bot.OPYS_KOROTKO)
print("ПАДІННЯ: " + ", ".join(bad) if bad else "усе зелене")
sys.exit(1 if bad else 0)
