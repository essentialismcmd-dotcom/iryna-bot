#!/usr/bin/env python3
"""
push1 на справжньому Postgres (13.10): PUSH_SQL зі store.py, bot.push1_segments і /push1 go на тих самих
людях, що в test_push1.py, але через справжні таблиці, kv_claim і журнал подій. G1 (урок 1.5 без схем)
отримує PDF схем і got_magnet_at, G2 (схеми без уроку і курсу) урок у кабінеті й подію lesson_gift, яку
PUSH_SQL далі рахує уроком. Потрібен pgserver (pip install pgserver: Postgres у тимчасовій теці, без
установки); без нього тест пропускається. Нікому нічого не шле: requests.post підставний.
Запуск: python -B test_push1_sql.py
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
MAGNIT = "https://test/magnit.pdf"
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "IRA_ID": "2",
                   "NO_THREADS": "1", "NOTIFY_IDS": "1,2", "CHANNEL_URL": "https://t.me/test_kanal",
                   "PUSH_SKIP_IDS": "901,902", "PUSH1_URL": "https://t.me/+TESTinvite", "MAGNET_URL": MAGNIT,
                   "KABINET_URL": "https://kab.test", "KABINET_KEY": "k", "DATABASE_URL": SRV.get_uri()})
for _k in ("PUSH1_G1", "PUSH1_G2", "PUSH1_KNOPKA", "PUSH1_UROK", "LEAD_IDS"):
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


def lyudyam(method=None):
    return sorted(p["chat_id"] for m, p in VYKLYKY if p.get("chat_id") not in (1, 2) and (method is None or m == method))


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

    def urok(uid, hours=72):
        podiia(uid, "retush_entry", {"tag": "retush"}, hours)

    def kv(k, v, mins=0):
        S.kv_set(k, v)
        Q("update kv set updated_at = now() - make_interval(mins => %s) where k = %s", (mins, k))

    lyudyna(1, "Yaro", magnet=True); podiia(1, "magnet")
    lyudyna(2, "Іра", role="ira"); kupivlia(2, "t1")
    # G1: урок 1.5 без схем
    lyudyna(102, "Урок", tag="retush"); urok(102)
    lyudyna(103, "Кабінет"); kv("kp:103:1.5:start", "1")
    lyudyna(121, "Урок і гайд", tag="retush"); urok(121); kupivlia(121, "t1")
    lyudyna(122, "Урок і курс", tag="retush"); urok(122); kupivlia(122, "k12")
    lyudyna(123, "Подарунок не дійшов", tag="retush"); urok(123); kv("gift:123", "1", mins=72 * 60)
    lyudyna(124, "Подарунок саме йде", tag="retush"); urok(124); kv("gift:124", "1", mins=5)
    # G2: схеми без уроку і курсу
    lyudyna(101, "Магніт", magnet=True); podiia(101, "magnet")
    lyudyna(105, "Схеми, заблокує", magnet=True)
    lyudyna(106, "Схеми і гайд", magnet=True); kupivlia(106, "t1")
    lyudyna(108, "Не оплатила", magnet=True); kupivlia(108, "k12z", "new")
    lyudyna(111, "Стопка", magnet=True); podiia(111, "message", {"text": "Дякую, стопка фото гарна"})
    lyudyna(113, "Повернулась", magnet=True); kv("blocked:113", "403", mins=96 * 60)
    # обидва
    lyudyna(107, "Курс і схеми", magnet=True); kupivlia(107, "k1")
    lyudyna(125, "Схеми і урок у подарунок", magnet=True); podiia(125, "lesson_gift", {"via": "push1"})
    lyudyna(126, "Обидва", magnet=True); urok(126)
    # ні схем, ні уроку
    lyudyna(104, "Гість МК", tag="mk_link"); kupivlia(104, "t1"); kupivlia(104, "k12")
    lyudyna(109, "Лише старт"); podiia(109, "start", {"tag": ""})
    kupivlia(120, "k12"); podiia(120, "give_manual", {"by": 1, "ok": True})
    # виключення
    lyudyna(110, "Стоп", magnet=True); podiia(110, "message", {"text": "Стоп, не треба"})
    lyudyna(117, "Відписка", tag="retush"); urok(117); podiia(117, "message", {"text": "Відпишіть мене будь ласка"})
    lyudyna(112, "Заблокувала", magnet=True); kv("blocked:112", "403", mins=48 * 60)
    lyudyna(114, "Свіжа", magnet=True); podiia(114, "magnet", hours=2)
    lyudyna(118, "Урок свіжий", days=0, tag="retush"); urok(118, hours=2)
    lyudyna(115, "Вже мала", magnet=True); kv("push1:115", "ok G2")
    lyudyna(901, "Тест", magnet=True)
    lyudyna(902, "Друг", tag="retush"); urok(902)
    kv("tag:101", "retush"); kv("pkb2:101", "1"); kv("mkn:kod", "3"); kv("kp:999:1.1:done", "1")   # чужі ключі kv

    rows = S.push_rows()
    ok("push_rows: рядок на кожного з users, покупок і подій", rows is not None
       and sorted(r["user_id"] for r in rows) == [1, 2, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112,
                                                  113, 114, 115, 117, 118, 120, 121, 122, 123, 124, 125, 126, 901, 902],
       str(sorted(r["user_id"] for r in rows or [])))
    rr = {r["user_id"]: r for r in rows or []}
    ok("push_rows: tiers список оплачених і виданих", sorted(rr[104]["tiers"]) == ["k12", "t1"] and rr[108]["tiers"] == []
       and rr[107]["tiers"] == ["k1"])
    ok("push_rows: магніт, урок, кабінет", rr[101]["ev_magnet"] and rr[102]["ev_lesson"] and rr[103]["kab_lesson"]
       and not rr[101]["kab_lesson"] and not rr[101]["ev_lesson"])
    ok("push_rows: подарований урок (lesson_gift) = урок", rr[125]["ev_lesson"] and not rr[125]["kab_lesson"])
    ok("push_rows: тексти повідомлень, push1, blocked_at", "Стоп, не треба" in rr[110]["texts"]
       and rr[115]["push1"] == "ok G2" and rr[112]["blocked_at"] is not None and rr[101]["blocked_at"] is None)

    SG = bot.push1_segments()
    ids = lambda lst: sorted(p["id"] for p in lst)
    ok("G1", ids(SG["seg"]["G1"]) == [102, 103, 121, 122, 123, 124], str(ids(SG["seg"]["G1"])))
    ok("G2", ids(SG["seg"]["G2"]) == [101, 105, 106, 108, 111, 113], str(ids(SG["seg"]["G2"])))
    sk = {w: ids(v) for w, v in SG["skip"].items()}
    ok("не шлемо", sk == {"персонал": [1], "вручну (PUSH_SKIP_IDS)": [901, 902], "push1 уже був": [115],
                          "заблокували бота": [112], "писали «стоп»": [110, 117], "бот писав за 24 год": [114, 118]},
       str(sk))
    ok("обидва 3 (курс і схеми, подарований урок, урок і схеми), ні того ні іншого 4", SG["both"] == 3
       and SG["none"] == 4, "%s %s" % (SG["both"], SG["none"]))

    app = bot.app.test_client()

    def go(n):
        VYKLYKY.clear()
        app.post("/sekret", json={"message": {"message_id": n, "chat": {"id": 1, "type": "private"},
                                              "from": {"id": 1, "first_name": "Yaro"}, "text": "/push1 go"}})

    go(1)
    ok("go: G1 PDF схем", lyudyam("sendDocument") == [102, 103, 121, 122, 123], str(lyudyam("sendDocument")))
    ok("go: G2 урок", lyudyam("sendMessage") == [101, 105, 106, 108, 111, 113], str(lyudyam("sendMessage")))
    ok("go: PDF схем з підписом G1", all(p["document"] == MAGNIT and p["caption"].startswith("Привіт, я Іра♥️ Дарую вам "
                                                                                             "свої 3 робочі схеми")
                                         for m, p in VYKLYKY if m == "sendDocument"))
    n = Q("select count(*) as n from kv where k like 'push1:%%'", (), fetch="one")["n"]
    ok("go: kv push1 у базі (11 + 115)", n == 12, str(n))
    ok("go: 403 = blocked:105 у базі", bool(S.kv_get("blocked:105")) and S.kv_get("push1:105") == "403 G2")
    m = Q("select user_id from users where got_magnet_at > now() - interval '1 minute' order by 1", (), fetch="all")
    ok("go: G1 тепер мають схеми в базі", [r["user_id"] for r in m] == [102, 103, 121, 122, 123], str(m))
    m = Q("select user_id from events where kind = 'magnet' and payload ->> 'via' = 'push1' order by 1", (), fetch="all")
    ok("go: подія magnet via push1", [r["user_id"] for r in m] == [102, 103, 121, 122, 123], str(m))
    m = Q("select user_id from events where kind = 'lesson_gift' and user_id <> 125 order by 1", (), fetch="all")
    ok("go: подія lesson_gift у G2 (крім 403)", [r["user_id"] for r in m] == [101, 106, 108, 111, 113], str(m))
    ok("go: заявка gift:<id> стоїть (подарунок після уроку не продублює)",
       all(S.kv_get("gift:%s" % u) for u in (102, 103, 121, 122, 123)))
    e = Q("select count(*) as n from events where kind = 'push1'", (), fetch="one")["n"]
    ok("go: подія push1 на кожного", e == 11, str(e))
    zv = [p.get("text") or "" for m, p in VYKLYKY if p.get("chat_id") == 1]
    ok("go: звіт адміну", any(z.startswith("push1 готово: надіслано 10 (G1 5, G2 5).")
                              and "Заблокували бота: 1 (id 105)" in z
                              and "(124 подарунок схем саме йде)" in z for z in zv), str(zv))
    go(2)
    ok("другий go: людям нічого (124 досі «саме йде»)", not lyudyam(), str(lyudyam()))
    kv("gift:124", "1", mins=60)
    go(3)
    ok("заявка gift за 15 хв застаріла: 124 отримує схеми", lyudyam() == [124] and S.kv_get("push1:124") == "ok G1")
    SG = bot.push1_segments()
    ok("після go: G1 і G2 порожні, усі в «обидва», у «push1 уже був» 403 і 115",
       not SG["seg"]["G1"] and not SG["seg"]["G2"] and SG["both"] == 3 + 6 + 5
       and ids(SG["skip"]["push1 уже був"]) == [105, 115], "%s %s" % (SG["both"], ids(SG["skip"]["push1 уже був"])))
    page = app.get("/push1/sekret").get_data(as_text=True)
    ok("сторінка /push1/<S>", "G1, брали урок 1.5, схем нема: дарую 3 схеми (PDF): 0" in page
       and "G2, брали схеми, уроку 1.5 не мали: дарую урок: 0" in page
       and "Мають і схеми, і урок 1.5 (чи курс): 14" in page)
finally:
    try:
        SRV.cleanup()
    except Exception:
        pass
    shutil.rmtree(TEKA, ignore_errors=True)

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
