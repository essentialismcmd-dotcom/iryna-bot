#!/usr/bin/env python3
"""
Посилання МК (13.10) БЕЗ мережі і бази: /start mk_<код> одразу дає гайд «Світло» і курс
ретуші без оплати, одне місце з ліміту на людину; повтор, закрите, місця скінчились,
вже мала курс, source_tag «mk», без paid_at, /mk stop|start, тиша для гостей МК;
mk, retush_liza і kurs10 як раніше. Код тут вигаданий, справжній лише в MK_LINK на Render.
Запуск: python -B test_mk_posylannia.py
"""
import os, sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KOD = "testkod777"     # вигаданий
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "NOTIFY_IDS": "1",
                   "CHANNEL_URL": "https://t.me/test_kanal", "COURSES_ON": "1",
                   "PAY_URL": "https://pay.test/jar", "COURSE_BUNDLE_ONLY": "1",
                   "COURSE1_FILES": "Урок 1 · основи > video:V1, document:D1 | Урок 2 · бʼюті > video:V2, document:D2",
                   "COURSE2_FILES": "", "KABINET_URL": "https://kab.test", "KABINET_KEY": "k",
                   "MK_LINK": KOD + ",3,2099-12-31"})
os.environ.pop("DATABASE_URL", None)

import requests
VYKLYKY = []
ZBII = set()          # chat_id, яким Telegram «не доставляє»


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    method = url.rsplit("/", 1)[-1]
    p = json or data or {}
    VYKLYKY.append((method, p))
    if p.get("chat_id") in ZBII:
        return _R({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
os.environ["FREE_LESSON"] = "1"   # 19.10: магніт уроку вимкнено за замовчуванням, тут перевіряємо його самого
import bot

bot.time.sleep = lambda s: None
bot.bg = lambda fn, *a, **kw: fn(*a, **kw)          # фон синхронно: перевірка без гонок
PUSH = []
bot.kabinet_mist.push_user = lambda uid: PUSH.append(uid)
app = bot.app.test_client()
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


# ---------- підставна база в памʼяті (та сама поведінка, що в store.py) ----------
DB = {"kv": {}, "users": {}, "purchases": {}, "events": []}


def _now():
    return datetime.now(timezone.utc)


def kv_take(k, limit):
    kv = DB["kv"]
    if k not in kv:
        kv[k] = "1"
        return "1"
    if int(kv[k]) < limit:
        kv[k] = str(int(kv[k]) + 1)
        return kv[k]
    return None


def touch_user(u, role="client", source_tag=None):
    uid = u.get("id")
    new = uid not in DB["users"]
    old = DB["users"].get(uid, {})
    DB["users"][uid] = dict(old, user_id=uid, username=u.get("username"), first_name=u.get("first_name"),
                            last_name=u.get("last_name"), role=role,
                            source_tag=old.get("source_tag") or source_tag or None)
    return dict(DB["users"][uid], is_new=new)


def add_purchase(uid, product, tier=None, order_code=None, amount_uah=None, source_tag=None):
    p = DB["purchases"].get(order_code)
    if p:
        p["amount_uah"] = amount_uah
        return dict(p)
    DB["purchases"][order_code] = p = {
        "user_id": uid, "product": product, "tier": tier, "order_code": order_code,
        "amount_uah": amount_uah, "status": "new", "created_at": _now(), "paid_at": None,
        "delivered_at": None,
        "source_tag": source_tag or DB["users"].get(uid, {}).get("source_tag")}
    return dict(p)


def ensure_purchase(uid, product, tier=None, order_code=None, amount_uah=None):
    if order_code in DB["purchases"]:
        return None
    return add_purchase(uid, product, tier, order_code, amount_uah,
                        DB["users"].get(uid, {}).get("source_tag"))


def mark_paid(oc, amount_uah=None):
    p = DB["purchases"].get(oc)
    if p and p["status"] == "new":
        p.update(status="paid", paid_at=_now())
        return dict(p)


def mark_delivered(oc):
    p = DB["purchases"].get(oc)
    if p:
        p.update(status="delivered", delivered_at=_now())
        return dict(p)


def purchases_of(uid, only_paid=True):
    return [dict(p) for p in DB["purchases"].values() if p["user_id"] == uid
            and (not only_paid or p["status"] in ("paid", "delivered"))]


def wipe_user(uid):
    DB["users"].pop(uid, None)
    for oc in [oc for oc, p in DB["purchases"].items() if p["user_id"] == uid]:
        DB["purchases"].pop(oc)
    DB["kv"].pop("tag:" + str(uid), None)
    return {"users": 1, "purchases": 0, "events": 0}


S = bot.store
S.ON = True
S.kv_get = lambda k, d=None: DB["kv"].get(k, d)
S.kv_set = lambda k, v: DB["kv"].__setitem__(k, str(v))
S.kv_claim = lambda k: (k not in DB["kv"], DB["kv"].setdefault(k, "1"))[0]
S.kv_take = kv_take
S.touch_user = touch_user
S.get_user = lambda uid: DB["users"].get(uid)
S.add_purchase = add_purchase
S.ensure_purchase = ensure_purchase
S.get_purchase = lambda oc: (dict(DB["purchases"][oc]) if oc in DB["purchases"] else None)
S.purchases_of = purchases_of
S.mark_paid = mark_paid
S.mark_delivered = mark_delivered
S.mark_magnet = lambda uid: None
S.log_event = lambda uid, kind, payload=None: DB["events"].append((uid, kind, payload))
S.wipe_user = wipe_user


def msg(text, uid, name="Гостя"):
    return app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": uid},
                    "from": {"id": uid, "first_name": name, "username": "u" + str(uid)}, "text": text}})


def sent(method="sendMessage", chat=None):
    return [p for m, p in VYKLYKY if m == method and (chat is None or p.get("chat_id") == chat)]


def teksty(chat):
    return [p.get("text") or p.get("caption") or "" for m, p in VYKLYKY if p.get("chat_id") == chat]


def knopky(p):
    return [b for r in (p.get("reply_markup") or {}).get("inline_keyboard", []) for b in r]


def mk_rows(uid):
    return {k: DB["purchases"].get(bot.mk_code(uid, k)) for k in ("t1", "k12")}


def staff(prefix):
    return [p for p in sent(chat=1) if (p.get("text") or "").startswith(prefix)]


# 1. Розбір MK_LINK
ok("розбір: змінна з Render", (bot.MK_CODE, bot.MK_SEATS, bot.MK_UNTIL) == (KOD, 3, "2099-12-31"))
ok("розбір: регістр і пробіли", bot.mk_link(" TestKod777 , 21 , 2026-10-14") == (KOD, 21, "2026-10-14"))
ok("розбір: порожня змінна закрита", bot.mk_link("") == ("", 0, ""))
ok("розбір: короткий код не код", bot.mk_link("ab1,21,2099-12-31")[0] == "")
ok("розбір: місця не число = 0", bot.mk_link(KOD + ",два,2099-12-31")[1] == 0)
ok("розбір: дата не за шаблоном", bot.mk_link(KOD + ",21,14.10.2026")[2] == "")
_kyiv_end = datetime(2026, 10, 14, 20, 59, tzinfo=timezone.utc)     # 23:59 за Києвом
_kyiv_next = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)     # 00:00 15.10 за Києвом
bot.MK_UNTIL = "2026-10-14"
ok("дата: останній день до 23:59 Києва відкритий", bot.mk_closed(_kyiv_end) == "")
ok("дата: наступна доба за Києвом закрита", bot.mk_closed(_kyiv_next) == "дата минула")
bot.MK_UNTIL = "2026-13-45"
ok("дата: неіснуюча закрита", bot.mk_closed() == "дата погана")
bot.MK_UNTIL = "2099-12-31"
ok("коди МК не IR: банкою не оплатити", not bot.CODE_RE.search(bot.mk_code(501, "k12"))
   and bot.mk_code(501, "t1").startswith("MK") and bot.mk_code(501, "k12").endswith("-6"))

# 2. Видача новій людині
VYKLYKY.clear(); PUSH.clear()
msg("/start mk_" + KOD, 501)
r = mk_rows(501)
ok("видача: два рядки, t1 і k12", r["t1"] and r["k12"] and r["t1"]["tier"] == "t1" and r["k12"]["tier"] == "k12")
ok("видача: delivered, ціна 0, без paid_at", all(p["status"] == "delivered" and p["amount_uah"] == 0
                                                  and p["paid_at"] is None and p["delivered_at"] for p in r.values()))
ok("видача: source_tag «mk»", all(p["source_tag"] == "mk" for p in r.values()))
ok("видача: доступ гайд і обидва курси", bot.owned_keys(501, real=True) == {"t1", "k1", "k2"})
ok("видача: кабінет отримав людину", 501 in PUSH)
t = teksty(501)
ok("видача: перше повідомлення MK_HELLO", t and t[0] == bot.MK_PAID_HELLO, t[0][:60] if t else "")
ok("видача: гайд документом", any(p.get("document") == "GUIDE" for p in sent("sendDocument", 501)))
ok("видача: інтро курсу і перший урок кнопкою в кабінет",
   any("Готово, курс ваш" in x for x in t)
   and any(b.get("web_app", {}).get("url") == "https://kab.test/?p=1.1" for p in sent(chat=501) for b in knopky(p)))
_order = [i for i, (m, p) in enumerate(VYKLYKY) if p.get("chat_id") == 501]
_hello = next(i for i in _order if VYKLYKY[i][1].get("text") == bot.MK_PAID_HELLO)
_guide = next(i for i in _order if VYKLYKY[i][1].get("document") == "GUIDE")
_intro = next(i for i in _order if "Готово, курс ваш" in (VYKLYKY[i][1].get("text") or ""))
ok("видача: порядок вітання, гайд, курс", _hello < _guide < _intro)
_ip = VYKLYKY[_intro][1]
ok("19.10: у вітанні курсу сказано, що відео в кабінеті, і є кнопка кабінету",
   "кабінеті" in _ip.get("text", "") and "kab.test" in str(_ip.get("reply_markup")), str(_ip.get("reply_markup"))[:120])
ok("видача: без підводки до продажу і без оплати",
   not any("Покажу мій курс" in x or "Оплатити" in x or "pay.test" in x for x in t)
   and not any("pay.test" in str(b) for p in sent(chat=501) for b in knopky(p)))
n = staff("МК: видано")
ok("сповіщення: місце 1 з 3, хто", len(n) == 1 and "місце 1 з 3" in n[0]["text"] and "id 501" in n[0]["text"]
   and "вже мала" not in n[0]["text"], n[0]["text"] if n else "")
ok("тиша: «Новий у боті» для гостя МК не йде", not staff("Новий у боті"))
ok("мітка в базі mk_link, не код", DB["users"][501]["source_tag"] == "mk_link"
   and (501, "start", {"tag": "mk_link"}) in DB["events"])
ok("код не потрапив у Telegram і події", KOD not in str(VYKLYKY) and KOD not in str(DB["events"]))
ok("лічильник місць 1", DB["kv"].get("mkn:" + KOD) == "1")
ok("подія mk_grant", any(e[1] == "mk_grant" and e[2]["seat"] == 1 and e[2]["of"] == 3 for e in DB["events"]))

# 3. Повтор: без нового місця, уроки кнопками
VYKLYKY.clear()
msg("/start mk_" + KOD, 501)
p = sent(chat=501)
ok("повтор: MK_AGAIN", p and p[-1]["text"] == bot.MK_AGAIN)
kb = [b.get("callback_data") for b in knopky(p[-1])]
ok("повтор: кнопки гайда й уроків", "my:guide" in kb and "les:k1:0" in kb, str(kb))
ok("повтор: місце не взято, сповіщень нема", DB["kv"].get("mkn:" + KOD) == "1" and not sent(chat=1))
ok("повтор: рядків так само два", len(purchases_of(501, only_paid=False)) == 2)

# 4. «Мої матеріали»
VYKLYKY.clear()
msg("Мої матеріали", 501)
p = sent(chat=501)[-1]
ok("Мої матеріали: гайд і уроки", p["text"] == bot.MOI_TEXT
   and {"my:guide", "les:k1:0", "les:k1:1"} <= {b.get("callback_data") for b in knopky(p)})

# 5. Неправильний код: закрите, кнопки ручної видачі, раз на добу
VYKLYKY.clear()
msg("/start mk_inshyikod9", 502)
ok("чужий код: MK_SHUT", teksty(502) == [bot.MK_SHUT], str(teksty(502)))
n = staff("МК НЕ видано")
ok("чужий код: персоналу «закрите: код не той» з кнопками курсу й гайду",
   len(n) == 1 and "(закрите: код не той)" in n[0]["text"] and "id 502" in n[0]["text"]
   and [b["callback_data"] for b in knopky(n[0])][:2] == ["give:502:k12", "give:502:t1"]
   and [b["callback_data"] for b in knopky(n[0])][2:] == ["napys:502", "podar:502"], str(n))
ok("чужий код: нічого не видано, місце не взято", not any(mk_rows(502).values()) and DB["kv"]["mkn:" + KOD] == "1")
VYKLYKY.clear()
msg("/start mk_inshyikod9", 502)
ok("чужий код вдруге: людині MK_SHUT, персоналу тиша", teksty(502) == [bot.MK_SHUT] and not staff("МК НЕ видано"))
VYKLYKY.clear()
msg("/start mk_", 509)
ok("порожній код: MK_SHUT", teksty(509) == [bot.MK_SHUT])

# 6. Місця скінчились (3)
for uid in (503, 504):
    msg("/start mk_" + KOD, uid)
ok("місця 2 і 3 видані", all(mk_rows(u)["k12"] for u in (503, 504)) and DB["kv"]["mkn:" + KOD] == "3")
VYKLYKY.clear()
msg("/start mk_" + KOD, 505)
ok("четвертому: MK_SHUT і «місць/бази нема»", teksty(505) == [bot.MK_SHUT]
   and any("(місць/бази нема)" in p["text"] for p in staff("МК НЕ видано")) and not any(mk_rows(505).values()))
VYKLYKY.clear()
msg("/mk", 1)
ok("/mk: видано 3 з 3, місця скінчились", "видано 3 з 3" in sent(chat=1)[-1]["text"]
   and "закрите: місця скінчились" in sent(chat=1)[-1]["text"], sent(chat=1)[-1]["text"])
bot.MK_SEATS = 100

# 7. Дата минула
bot.MK_UNTIL = "2020-01-01"
VYKLYKY.clear()
msg("/start mk_" + KOD, 506)
ok("дата минула: MK_SHUT, «закрите: дата минула»", teksty(506) == [bot.MK_SHUT]
   and any("(закрите: дата минула)" in p["text"] for p in staff("МК НЕ видано")))
bot.MK_UNTIL = "2099-12-31"

# 8. /mk stop і /mk start
VYKLYKY.clear()
msg("/mk", 1)
s = sent(chat=1)[-1]["text"]
ok("/mk: видано, до дати, відкрите", "видано 3 з 100" in s and "до 31.12.2099" in s and "відкрите" in s
   and KOD not in s, s)
msg("/mk stop", 1)
ok("/mk stop: закрите", "закрите: зупинено /mk stop" in sent(chat=1)[-1]["text"])
VYKLYKY.clear()
msg("/start mk_" + KOD, 507)
ok("після /mk stop правильний код не видає", teksty(507) == [bot.MK_SHUT] and not any(mk_rows(507).values()))
msg("/mk start", 1)
ok("/mk start: відкрите знову", "відкрите" in sent(chat=1)[-1]["text"] and "закрите" not in sent(chat=1)[-1]["text"])
VYKLYKY.clear()
msg("/mk", 508)
ok("/mk не персоналу: статусу нема", not any("Посилання МК" in x for x in teksty(508)))

# 9. Вже мала курс (оплата k12z): курс не шлемо вдруге, уроки кнопками
add_purchase(510, "course", "k12z", "IR" + bot.b36(510) + "-7", 2970)
mark_paid("IR" + bot.b36(510) + "-7")
VYKLYKY.clear()
msg("/start mk_" + KOD, 510)
t = teksty(510)
ok("вже мала курс: вітання, гайд, «Курс ретуші вже ваш»", t[0] == bot.MK_PAID_HELLO and bot.COURSE_OWNED in t
   and not any("Готово, курс ваш" in x for x in t)
   and any(p.get("document") == "GUIDE" for p in sent("sendDocument", 510)), str(t))
ok("вже мала курс: у сповіщенні", any("(вже мала: курс)" in p["text"] for p in staff("МК: видано")))

# 10. Партнерська мітка не переходить на МК-рядки
msg("/start retush_liza", 511)
msg("/start mk_" + KOD, 511)
ok("людина Лізи: МК-рядки з source_tag «mk»", all(p and p["source_tag"] == "mk" for p in mk_rows(511).values())
   and DB["users"][511]["source_tag"] == "retush_liza")

# 11. Telegram не доставив: доступ усе одно записаний
ZBII.add(512); VYKLYKY.clear()
msg("/start mk_" + KOD, 512)
ZBII.discard(512)
ok("збій Telegram: рядки delivered", all(p and p["status"] == "delivered" for p in mk_rows(512).values()))
n = staff("МК: видано")
ok("збій Telegram: персонал знає (гайд у МК-сповіщенні, урок своїм сповіщенням)",
   n and "Гайд у чат не пішов" in n[-1]["text"] and staff("Урок k1 №1 для id 512"), n[-1]["text"] if n else "")

# 12. /skyd стирає МК-рядки, лічильник лишається; наступний вхід бере нове місце
_was = DB["kv"]["mkn:" + KOD]
wipe_user(501)
ok("skyd: МК-рядків нема, лічильник той самий", not any(mk_rows(501).values()) and DB["kv"]["mkn:" + KOD] == _was)
VYKLYKY.clear()
msg("/start mk_" + KOD, 501)
ok("skyd: знову MK_HELLO і нове місце", teksty(501)[0] == bot.MK_PAID_HELLO and DB["kv"]["mkn:" + KOD] == str(int(_was) + 1))


# 13. Тиша кабінету для гостей МК, звичайні люди як раніше
def podiia(uid, kind, lesson):
    return app.post("/kabinet-podiia", headers={"X-Kabinet-Key": "k"},
                    json={"user_id": uid, "kind": kind, "lesson": lesson})


bot.magnet_ref = lambda: "MAGNETFILE"
VYKLYKY.clear()
podiia(501, "start", "1.1"); podiia(501, "done", "1.3")
ok("кабінет: гостю МК персоналу тиша", not sent(chat=1))
ok("кабінет: гостю МК подарунка нема", not sent("sendDocument", 501))
VYKLYKY.clear()
touch_user({"id": 520, "first_name": "Учениця"})
podiia(520, "start", "1.1")
ok("кабінет: звичайній людині сповіщення як раніше", any("почала урок 1.1" in p["text"] for p in sent(chat=1)))

# 14. mk, retush_liza, kurs10 як раніше
VYKLYKY.clear()
msg("/start mk", 530)
ok("mk: привітання МК і кнопка «Дізнатися детальніше» (20.10)", any(p.get("text") == bot.MK_HELLO and knopky(p)[0].get("callback_data") == "mk"
                                      for p in sent(chat=530)))
ok("mk: «Новий у боті», мітка mk", any("Мітка: mk" in p["text"] for p in staff("Новий у боті")))
VYKLYKY.clear()
msg("/start retush_liza", 531)
card = sent("sendPhoto", 531) or sent("sendMessage", 531)
ok("retush_liza: магніт уроку", card and "Маски: волосся і фон" in (card[0].get("caption") or card[0].get("text") or ""))
ok("retush_liza: source_tag і підпис партнера", DB["users"][531]["source_tag"] == "retush_liza"
   and any("(від Лізи (liza.khbchk))" in p["text"] for p in staff("Новий у боті")))
VYKLYKY.clear()
msg("/start kurs10", 532)
p = sent(chat=532)
ok("kurs10: картка курсу зі знижкою і код -7", p and "знижка 10 %" in p[-1]["text"]
   and "впишіть" not in p[-1]["text"] and ("IR" + bot.b36(532) + "-7") in bot.pay_url(532, "k12z"),
   p[-1]["text"][:80] if p else "")
ok("kurs10: «Новий у боті» з кнопкою «Видати курс вручну»",
   any(knopky(x) and knopky(x)[0]["text"] == "Видати курс вручну" for x in staff("Новий у боті")))

# 15. Без бази (staging): правильний код = «місць/бази нема»
S.ON = False
S.kv_take = lambda k, limit: None
_kv = S.kv_get
S.kv_get = lambda k, d=None: None
VYKLYKY.clear()
msg("/start mk_" + KOD, 540)
ok("без бази: MK_SHUT і «місць/бази нема»", teksty(540) == [bot.MK_SHUT]
   and any("(місць/бази нема)" in p["text"] for p in staff("МК НЕ видано")))
msg("/mk", 1)
ok("без бази: /mk так і каже", "Бази нема" in sent(chat=1)[-1]["text"])
S.ON, S.kv_take, S.kv_get = True, kv_take, _kv

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
