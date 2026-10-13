#!/usr/bin/env python3
"""
Сторінка /lyudy/<S> (13.10) на справжньому Postgres: люди з бази одним заходом (store.people_data), етап одним
словом, що отримала, коли і як (оплата, вручну, МК), урок 1.5 з кабінету, заявка МК, канал через getChatMember
(підставний), позначки (персонал, LYUDY_MARKS), зведення, HTML з екрануванням і ?md=1. Потрібен pgserver
(pip install pgserver); без нього тест пропускається. Нікому нічого не шле: requests.post підставний.
Запуск: python -B test_lyudy.py
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

TEKA = tempfile.mkdtemp(prefix="lyudypg")
SRV = pgserver.get_server(TEKA, cleanup_mode="stop")
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "IRA_ID": "2",
                   "NO_THREADS": "1", "NOTIFY_IDS": "1,2", "CHANNEL_URL": "https://t.me/test_kanal",
                   "LYUDY_MARKS": "901:тест, 686405950:акаунт Yaro,674792338:друг Yaro, погане:х",
                   "DATABASE_URL": SRV.get_uri()})
for _k in ("LEAD_IDS", "CHANNEL_ID"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []
KANAL = {201: {"status": "member"}, 202: {"status": "left"}, 203: {"status": "member"},
         204: {"status": "administrator"}, 205: {"status": "kicked"}, 206: {"status": "restricted", "is_member": True},
         208: {"status": "restricted", "is_member": False}, 209: {"status": "member"}, 1: {"status": "creator"}}


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    p = json or data or {}
    m = url.rsplit("/", 1)[-1]
    VYKLYKY.append((m, p))
    if m == "getChatMember":
        r = KANAL.get(p.get("user_id"))
        if r is None:
            return _R({"ok": False, "error_code": 400, "description": "Bad Request: user not found"})
        return _R({"ok": True, "result": dict(r, user={"id": p.get("user_id")})})
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import bot

S = bot.store
bot.time.sleep = lambda s: None
bot.kabinet_mist.push_user = lambda uid: None
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


try:
    ok("база жива, схема стала", S.ON and S._ensure())
    Q = S.q

    def lyudyna(uid, name, days=3, tag=None, magnet=False, role="client", username=True):
        S.touch_user({"id": uid, "username": ("u" + str(uid)) if username else None, "first_name": name},
                     role=role, source_tag=tag)
        Q("update users set last_seen_at = now() - make_interval(days => %s), created_at = now() - make_interval(days => %s), "
          "got_magnet_at = case when %s then now() - make_interval(days => %s) end where user_id = %s",
          (days, days + 1, magnet, days, uid))

    def kupivlia(uid, tier, status="delivered", code=None, amount=900, tag=None):
        oc = code or bot.order_code(uid, tier)
        S.add_purchase(uid, "course" if tier.startswith("k") else "guide", tier=tier, order_code=oc,
                       amount_uah=amount, source_tag=tag)
        if status in ("paid", "delivered"):
            S.mark_paid(oc)
        if status == "delivered":
            S.mark_delivered(oc)
        return oc

    def podiia(uid, kind, payload=None, hours=None):
        S.log_event(uid, kind, payload)
        if hours is not None:
            Q("update events set created_at = now() - make_interval(hours => %s) "
              "where id = (select max(id) from events where user_id = %s)", (hours, uid))

    def kv(k, v, hours=0):
        S.kv_set(k, v)
        Q("update kv set updated_at = now() - make_interval(hours => %s) where k = %s", (hours, k))

    lyudyna(1, "Yaro", magnet=True); podiia(1, "magnet")
    lyudyna(2, "Іра", role="ira")
    lyudyna(201, "Схеми", tag="inst", magnet=True); podiia(201, "start", {"tag": "inst"}, hours=80); podiia(201, "magnet", hours=79)
    lyudyna(202, "Урок", tag="retush"); podiia(202, "retush_entry", {"tag": "retush"}, hours=70)
    kv("kp:202:1.5:start", "1", hours=69)
    lyudyna(203, "Обидва", tag="retush_olia"); podiia(203, "retush_entry", {"tag": "retush"}, hours=60)
    kv("kp:203:1.5:start", "1", hours=59); kv("kp:203:1.5:done", "1", hours=58)
    podiia(203, "magnet", {"via": "gift"}, hours=58); Q("update users set got_magnet_at = now() - interval '58 hours' where user_id = 203")
    lyudyna(204, "Гайд оплата", tag="guide"); oc204 = kupivlia(204, "t1"); podiia(204, "pay_ok", {"code": oc204})
    lyudyna(205, "Курс вручну", tag="retush"); kupivlia(205, "k12", amount=3300); podiia(205, "give_manual", {"by": 1, "ok": True})
    kv("kp:205:1.1:start", "1"); kv("kp:205:1.1:done", "1"); kv("kp:205:1.2:start", "1")
    lyudyna(206, "Гостя МК", tag="mk_link")
    for t in ("t1", "k12"):
        kupivlia(206, t, code=bot.mk_code(206, t), amount=0, tag="mk")
    podiia(206, "mk_grant", {"seat": 1, "of": 30, "had": []})
    lyudyna(207, "<b>Старт</b> & заявка", username=False); podiia(207, "start", {"tag": ""})
    podiia(207, "mk_want"); podiia(207, "mk_want"); kv("blocked:207", "Forbidden: bot was blocked by the user")
    Q("update users set last_seen_at = now() - interval '5 days' where user_id = 207")
    lyudyna(208, "Обрала тариф"); kupivlia(208, "t1", status="new"); podiia(208, "tier_pick", {"tier": "t1"})
    lyudyna(209, "Курс знижка", tag="kurs10"); oc209 = kupivlia(209, "k12z", amount=2970); podiia(209, "pay_ok", {"code": oc209})
    podiia(209, "message", {"text": "Дякую!"}); podiia(209, "message", {"text": "Все працює"})
    lyudyna(210, "Стара покупка"); kupivlia(210, "t1")
    Q("update purchases set paid_at = now() - interval '20 days', delivered_at = now() - interval '20 days' where user_id = 210")
    lyudyna(901, "Тест", magnet=True); kv("push1:901", "ok A")
    lyudyna(686405950, "Incognito"); kupivlia(686405950, "k12", amount=3300); podiia(686405950, "give_manual", {"by": 1, "ok": True})

    d = S.people_data()
    ok("people_data: чотири частини", d is not None and set(d) == {"users", "purchases", "events", "kv"})
    ev205 = [e for e in d["events"] if e["user_id"] == 205 and e["kind"] == "give_manual"]
    ok("people_data: усі часи й payload ручної видачі", len(ev205) == 1 and len(ev205[0]["all_at"]) == 1
       and ev205[0]["all_p"][0].get("ok") is True)
    ok("people_data: kv лише людські ключі", all(r["k"].split(":")[0] in ("kp", "blocked", "push1", "gift", "pkb",
                                                                        "pkb2", "tag") for r in d["kv"]))

    app = bot.app.test_client()
    VYKLYKY.clear()
    r = app.get("/lyudy/sekret")
    html_ = r.get_data(as_text=True)
    ok("сторінка відкривається", r.status_code == 200 and "<h1>Люди бота</h1>" in html_)
    ok("сторінка для телефона (viewport)", 'name="viewport"' in html_)
    gcm = [p for m, p in VYKLYKY if m == "getChatMember"]
    ok("getChatMember на кожну людину, канал з CHANNEL_URL", len(gcm) == 14 and all(p["chat_id"] == "@test_kanal" for p in gcm),
       str(len(gcm)))
    ok("людям нічого не надіслано", not [m for m, p in VYKLYKY if m != "getChatMember"])

    rows = {x["id"]: x for x in bot.lyudy_rows(S.people_data())}
    kan = bot.kanal_many(list(rows))
    for x in rows.values():
        x["kanal"] = kan[x["id"]]
    st = {i: x["stage"] for i, x in rows.items()}
    ok("етапи", st[201] == "схеми" and st[202] == "урок" and st[203] == "урок" and st[204] == "гайд"
       and st[205] == "курс" and st[206] == "МК" and st[207] == "старт" and st[208] == "старт" and st[209] == "курс"
       and st[210] == "гайд", str(st))
    f = lambda i, n: dict(rows[i]["f"])[n]
    ok("гайд оплатою з сумою", "Гайд «Світло» (t1)" in f(204, "гайд") and "оплата, 900 грн" in f(204, "гайд"), f(204, "гайд"))
    ok("курс вручну", ", вручну" in f(205, "курс") and "грн" not in f(205, "курс"), f(205, "курс"))
    ok("курс зі знижкою оплатою", "(k12z)" in f(209, "курс") and "оплата, 2970 грн" in f(209, "курс"), f(209, "курс"))
    ok("МК: гайд і курс з позначкою МК", ", МК" in f(206, "гайд") and ", МК" in f(206, "курс")
       and f(206, "МК").startswith("гість за посиланням МК"), f(206, "МК"))
    ok("стара покупка без подій: спосіб невідомий", "спосіб невідомий" in f(210, "гайд"))
    ok("обрала тариф без оплати", f(208, "гайд").startswith("обрала t1") and "не оплачено" in f(208, "гайд"))
    ok("схеми: кнопка і подарунок", "кнопка «Забрати три схеми»" in f(201, "3 схеми")
       and "подарунок після уроку" in f(203, "3 схеми"), f(203, "3 схеми"))
    ok("урок 1.5: вхід, відкрила, додивилась", f(203, "урок 1.5").count("—") == 0 and "додивилась —" in f(202, "урок 1.5")
       and f(201, "урок 1.5") == "—", f(202, "урок 1.5"))
    ok("кабінет: інші частини курсу", f(205, "кабінет, інші частини") == "почала 2, додивилась 1", f(205, "кабінет, інші частини"))
    ok("заявка МК з кількістю натискань", f(207, "МК").startswith("заявка ") and "(натискань: 2)" in f(207, "МК"), f(207, "МК"))
    ok("писала боту", f(209, "писала боту").startswith("2, останнє"))
    ok("заблокувала бота", rows[207]["blocked"] and "заблокувала бота" in dict(rows[207]["f"]))
    ok("прийшла: мітка і без мітки", f(203, "прийшла").startswith("retush_olia, ") and f(207, "прийшла").startswith("без мітки, "))
    ok("позначки: персонал і LYUDY_MARKS", rows[1]["marks"] == ["персонал"] and rows[2]["marks"] == ["персонал"]
       and rows[901]["marks"] == ["тест"] and rows[686405950]["marks"] == ["акаунт Yaro"] and not rows[201]["marks"])
    ok("канал: так, ні, обмеження, невідомо", rows[201]["kanal"] == (True, "так") and rows[202]["kanal"] == (False, "ні")
       and rows[206]["kanal"][0] is True and rows[208]["kanal"] == (False, "ні") and rows[205]["kanal"][0] is False
       and rows[207]["kanal"][0] is None and "user not found" in rows[207]["kanal"][1])
    ok("останній дотик: найсвіжіше", "(писала чи тиснула в боті)" in f(205, "останній дотик")
       or "(ручна видача)" in f(205, "останній дотик"), f(205, "останній дотик"))

    sm = bot.lyudy_summary(list(rows.values()))
    tab = {s: (n, k) for s, n, k in sm["table"]}
    ok("зведення: етапи і канал", tab == {"МК": (1, 1), "курс": (2, 1), "гайд": (2, 1), "урок": (2, 1), "схеми": (1, 1),
                                          "старт": (2, 0)}, str(tab))
    ok("зведення: безкоштовне без покупок", "лише схеми 1, лише урок 1.5 1, обидва 1" in sm["lines"][2], sm["lines"][2])
    ok("зведення: у каналі і невідомо", sm["lines"][1].startswith("У каналі: 5 з 10; невідомо 2 ("), sm["lines"][1])
    ok("зведення: заявки, блоки", "Заявок на МК (людей): 1; гостей МК: 1." == sm["lines"][3]
       and sm["lines"][4].startswith("Заблокували бота: 1;"), sm["lines"][3] + " | " + sm["lines"][4])

    ok("HTML екранує імена", "&lt;b&gt;Старт&lt;/b&gt; &amp; заявка" in html_ and "<b>Старт</b>" not in html_)
    ok("HTML: розділ персоналу наприкінці", html_.index("Персонал і позначені") > html_.index("старт: лише /start"))
    VYKLYKY.clear()
    md = app.get("/lyudy/sekret?md=1")
    mdt = md.get_data(as_text=True)
    ok("?md=1: Markdown з карткою на людину", md.status_code == 200 and "text/markdown" in md.headers["Content-Type"]
       and mdt.count("\n### ") == 14 and "| етап | людей | у каналі |" in mdt)
    ok("кеш каналу: друге відкриття без getChatMember", not VYKLYKY, str(len(VYKLYKY)))
    ok("чужий секрет: 404", app.get("/lyudy/inshyi").status_code == 404)
    if os.getenv("LYUDY_DUMP"):          # подивитись очима: LYUDY_DUMP=<тека> python -B test_lyudy.py
        open(os.path.join(os.getenv("LYUDY_DUMP"), "lyudy.html"), "w", encoding="utf-8").write(html_)
        open(os.path.join(os.getenv("LYUDY_DUMP"), "lyudy.md"), "w", encoding="utf-8").write(mdt)
    S.ON = False
    try:
        t = app.get("/lyudy/sekret").get_data(as_text=True)
        ok("без бази: чесно каже", "База вимкнена" in t)
    finally:
        S.ON = True
finally:
    try:
        SRV.cleanup()
    except Exception:
        pass
    shutil.rmtree(TEKA, ignore_errors=True)

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
