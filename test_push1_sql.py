#!/usr/bin/env python3
"""
push1 на справжньому Postgres (13.10): PUSH_SQL зі store.py, bot.push1_segments і /push1 go на тих
самих людях, що в test_push1.py, але через справжні таблиці, kv_claim і журнал подій. Потрібен pgserver
(pip install pgserver: Postgres у тимчасовій теці, без установки); без нього тест пропускається.
Нікому нічого не шле: requests.post підставний. Запуск: python -B test_push1_sql.py
"""
import os, sys, tempfile, shutil

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import pgserver
except ImportError:
    print("pgserver нема (pip install pgserver): тест на Postgres пропущено")
    sys.exit(0)

TEKA = tempfile.mkdtemp(prefix="push1pg")
SRV = pgserver.get_server(TEKA, cleanup_mode="stop")
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "IRA_ID": "2",
                   "NO_THREADS": "1", "NOTIFY_IDS": "1,2", "CHANNEL_URL": "https://t.me/test_kanal",
                   "PUSH_SKIP_IDS": "901,902", "PUSH1_URL": "https://t.me/+TESTinvite",
                   "DATABASE_URL": SRV.get_uri()})
for _k in ("PUSH1_A", "PUSH1_B", "PUSH1_G", "PUSH1_KNOPKA", "LEAD_IDS"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    p = json or data or {}
    VYKLYKY.append((url.rsplit("/", 1)[-1], p))
    if p.get("chat_id") == 105:
        return _R({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import bot

S = bot.store
bot.time.sleep = lambda s: None
bot.kabinet_mist.push_user = lambda uid: None
bot.push1_spawn = lambda fn: fn()
bot.kyiv_hour = lambda now=None: 12
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


try:
    ok("база жива, схема стала", S.ON and S._ensure())
    Q = S.q

    def lyudyna(uid, name, days=3, tag=None, magnet=False, role="client"):
        S.touch_user({"id": uid, "username": "u" + str(uid), "first_name": name}, role=role, source_tag=tag)
        Q("update users set last_seen_at = now() - make_interval(days => %s), "
          "got_magnet_at = case when %s then now() - make_interval(days => %s) end where user_id = %s",
          (days, magnet, days, uid))

    def kupivlia(uid, tier, status="delivered"):
        oc = "T%s-%s" % (uid, tier)
        S.add_purchase(uid, "course" if tier.startswith("k") else "guide", tier=tier, order_code=oc, amount_uah=1)
        if status in ("paid", "delivered"):
            S.mark_paid(oc)
        if status == "delivered":
            S.mark_delivered(oc)

    def podiia(uid, kind, payload=None, hours=72):
        S.log_event(uid, kind, payload)
        Q("update events set created_at = now() - make_interval(hours => %s) "
          "where id = (select max(id) from events where user_id = %s)", (hours, uid))

    def kv(k, v, hours=0):
        S.kv_set(k, v)
        Q("update kv set updated_at = now() - make_interval(hours => %s) where k = %s", (hours, k))

    lyudyna(1, "Yaro", magnet=True); podiia(1, "magnet")
    lyudyna(2, "Іра", role="ira"); kupivlia(2, "t1")
    lyudyna(101, "Магніт", magnet=True); podiia(101, "magnet")
    lyudyna(102, "Урок", tag="retush"); podiia(102, "retush_entry", {"tag": "retush"})
    lyudyna(103, "Кабінет"); kv("kp:103:1.5:start", "1")
    lyudyna(108, "Не оплатила", magnet=True); kupivlia(108, "k12z", "new")
    lyudyna(111, "Стопка", magnet=True); podiia(111, "message", {"text": "Дякую, стопка фото гарна"})
    lyudyna(113, "Повернулась", magnet=True); kv("blocked:113", "403", hours=96)
    lyudyna(104, "Гість МК", tag="mk_link"); kupivlia(104, "t1"); kupivlia(104, "k12")
    lyudyna(105, "Курс, заблокувала"); kupivlia(105, "k12z", "paid")
    lyudyna(107, "Курс і гайд"); kupivlia(107, "t1"); kupivlia(107, "k1")
    kupivlia(120, "k12"); podiia(120, "give_manual", {"by": 1, "ok": True})
    lyudyna(106, "Гайд", magnet=True); kupivlia(106, "t1")
    lyudyna(118, "Гайд свіжий", days=0); kupivlia(118, "t1")
    lyudyna(109, "Лише старт"); podiia(109, "start", {"tag": ""})
    lyudyna(110, "Стоп", magnet=True); podiia(110, "message", {"text": "Стоп, не треба"})
    lyudyna(117, "Відписка", tag="retush"); podiia(117, "message", {"text": "Відпишіть мене будь ласка"})
    lyudyna(112, "Заблокувала", magnet=True); kv("blocked:112", "403", hours=48)
    lyudyna(114, "Свіжа", magnet=True); podiia(114, "magnet", hours=2)
    lyudyna(115, "Вже мала", magnet=True); kv("push1:115", "ok A")
    lyudyna(901, "Тест", magnet=True)
    lyudyna(902, "Друг"); kupivlia(902, "k12")
    kv("tag:101", "retush"); kv("pkb:101", "1"); kv("mkn:kod", "3"); kv("kp:999:1.1:done", "1")   # чужі ключі kv

    rows = S.push_rows()
    ok("push_rows: рядок на кожного з users, покупок і подій", rows is not None
       and sorted(r["user_id"] for r in rows) == [1, 2, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112,
                                                  113, 114, 115, 117, 118, 120, 901, 902],
       str(sorted(r["user_id"] for r in rows or [])))
    rr = {r["user_id"]: r for r in rows or []}
    ok("push_rows: tiers список оплачених і виданих", sorted(rr[107]["tiers"]) == ["k1", "t1"] and rr[108]["tiers"] == []
       and rr[105]["tiers"] == ["k12z"])
    ok("push_rows: магніт, урок, кабінет", rr[101]["ev_magnet"] and rr[102]["ev_lesson"] and rr[103]["kab_lesson"]
       and not rr[101]["kab_lesson"])
    ok("push_rows: тексти повідомлень, push1, blocked_at", "Стоп, не треба" in rr[110]["texts"]
       and rr[115]["push1"] == "ok A" and rr[112]["blocked_at"] is not None and rr[101]["blocked_at"] is None)

    SG = bot.push1_segments()
    ids = lambda lst: sorted(p["id"] for p in lst)
    ok("A", ids(SG["seg"]["A"]) == [101, 102, 103, 108, 111, 113], str(ids(SG["seg"]["A"])))
    ok("B", ids(SG["seg"]["B"]) == [104, 105, 107, 120], str(ids(SG["seg"]["B"])))
    ok("G", ids(SG["seg"]["G"]) == [106], str(ids(SG["seg"]["G"])))
    sk = {w: ids(v) for w, v in SG["skip"].items()}
    ok("не шлемо", sk == {"персонал": [1, 2], "вручну (PUSH_SKIP_IDS)": [901, 902], "push1 уже був": [115],
                          "заблокували бота": [112], "писали «стоп»": [110, 117], "бот писав за 24 год": [114, 118]},
       str(sk))
    ok("решта", SG["rest"] == 1)

    app = bot.app.test_client()
    app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": 1, "type": "private"},
                                          "from": {"id": 1, "first_name": "Yaro"}, "text": "/push1 go"}})
    lyudi = sorted(p["chat_id"] for m, p in VYKLYKY if m == "sendMessage" and p.get("chat_id") not in (1, 2))
    ok("go: кому пішло", lyudi == [101, 102, 103, 104, 105, 107, 108, 111, 113, 120], str(lyudi))
    n = Q("select count(*) as n from kv where k like 'push1:%%'", (), fetch="one")["n"]
    ok("go: kv push1 у базі (10 + 115)", n == 11, str(n))
    ok("go: 403 = blocked:105 у базі", bool(S.kv_get("blocked:105")) and S.kv_get("push1:105") == "403 B")
    e = Q("select count(*) as n from events where kind = 'push1'", (), fetch="one")["n"]
    ok("go: подія push1 на кожного", e == 10, str(e))
    ok("go: звіт адміну", any((p.get("text") or "").startswith("push1 готово: надіслано 9 (A 6, B 3).")
                              for m, p in VYKLYKY if p.get("chat_id") == 1))
    VYKLYKY.clear()
    app.post("/sekret", json={"message": {"message_id": 2, "chat": {"id": 1, "type": "private"},
                                          "from": {"id": 1, "first_name": "Yaro"}, "text": "/push1 go"}})
    ok("другий go: людям нічого", not [p for m, p in VYKLYKY if p.get("chat_id") not in (1, 2)])
    ok("сторінка /push1/<S>", "A, магніт чи урок 1.5, без покупок: 0" in app.get("/push1/sekret").get_data(as_text=True))
finally:
    try:
        SRV.cleanup()
    except Exception:
        pass
    shutil.rmtree(TEKA, ignore_errors=True)

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
