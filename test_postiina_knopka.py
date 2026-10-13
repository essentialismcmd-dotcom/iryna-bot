#!/usr/bin/env python3
"""
Постійна клавіатура «Мої матеріали» + «Канал «для своїх»» в кожного з першого /start (13.10) БЕЗ мережі
і бази. Кожен приватний /start і перше повідомлення людини без прапорця pkb2:<id> отримують її рівно раз:
на відповіді без своєї клавіатури або рядком-носієм PERSIST_LINE у кінці апдейту. Стара клавіатура
(прапорець pkb:<id>, лише «Мої матеріали») міняється на нову при наступному зверненні, без розсилки.
Натиснута кнопка каналу = нова вже є; на неї рядок Іри з інлайн-кнопкою в канал (запрошення knopka),
подія kanal_btn, персоналу нічого. Не Ірі, не в групі, не в сповіщеннях персоналу, без розсилки
(натискання інлайн-кнопок рядка не дають). Код МК і запрошення тут вигадані.
Запуск: python -B test_postiina_knopka.py
"""
import os, sys, time, inspect
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KOD = "testkod777"     # вигаданий
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "IRA_ID": "7", "NOTIFY_IDS": "1,7", "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE",
                   "CHANNEL_URL": "https://t.me/test_kanal", "COURSES_ON": "1",
                   "PAY_URL": "https://pay.test/jar", "COURSE_BUNDLE_ONLY": "1",
                   "COURSE1_FILES": "Урок 1 · основи > video:V1, document:D1 | Урок 2 · бʼюті > video:V2, document:D2",
                   "COURSE2_FILES": "", "KABINET_URL": "https://kab.test", "KABINET_KEY": "k",
                   "MK_LINK": KOD + ",3,2099-12-31", "KANAL_KNOPKA_URL": "https://t.me/+TESTknopka"})
for _k in ("DATABASE_URL", "IRA_ON", "START_PIC", "KANAL_BTN_TEXT"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    method = url.rsplit("/", 1)[-1]
    p = json or data or {}
    VYKLYKY.append((method, p))
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import bot
import store as store_mod

bot.time.sleep = lambda s: None
bot.bg = lambda fn, *a, **kw: fn(*a, **kw)          # фон синхронно: перевірка без гонок
bot.kabinet_mist.push_user = lambda uid: None
app = bot.app.test_client()
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


# ---------- підставна база в памʼяті ----------
DB = {"kv": {}, "users": {}, "purchases": {}, "events": []}


def _now():
    return datetime.now(timezone.utc)


def kv_take(k, limit):
    kv = DB["kv"]
    n = int(kv.get(k, "0"))
    if n >= limit:
        return None
    kv[k] = str(n + 1)
    return kv[k]


def touch_user(u, role="client", source_tag=None):
    uid = u.get("id")
    new = uid not in DB["users"]
    old = DB["users"].get(uid, {})
    DB["users"][uid] = dict(old, user_id=uid, username=u.get("username"), first_name=u.get("first_name"),
                            role=role, source_tag=old.get("source_tag") or source_tag or None)
    return dict(DB["users"][uid], is_new=new)


def add_purchase(uid, product, tier=None, order_code=None, amount_uah=None, source_tag=None):
    p = DB["purchases"].get(order_code)
    if p:
        return dict(p)
    DB["purchases"][order_code] = p = {
        "user_id": uid, "product": product, "tier": tier, "order_code": order_code,
        "amount_uah": amount_uah, "status": "new", "created_at": _now(), "paid_at": None,
        "delivered_at": None, "source_tag": source_tag}
    return dict(p)


def mark_delivered(oc):
    p = DB["purchases"].get(oc)
    if p:
        p.update(status="delivered", delivered_at=_now())
        return dict(p)


def purchases_of(uid, only_paid=True):
    return [dict(p) for p in DB["purchases"].values() if p["user_id"] == uid
            and (not only_paid or p["status"] in ("paid", "delivered"))]


def wipe_user(uid):      # як store.wipe_user: рядки людини і її kv tag:/pkb:/pkb2:
    DB["users"].pop(uid, None)
    for oc in [oc for oc, p in DB["purchases"].items() if p["user_id"] == uid]:
        DB["purchases"].pop(oc)
    for k in ("tag:" + str(uid), "pkb:" + str(uid), "pkb2:" + str(uid)):
        DB["kv"].pop(k, None)
    return {"users": 1, "purchases": 0, "events": 0}


ORIG_WIPE = store_mod.wipe_user
S = bot.store
S.ON = True
S.kv_get = lambda k, d=None: DB["kv"].get(k, d)
S.kv_set = lambda k, v: DB["kv"].__setitem__(k, str(v))
S.kv_claim = lambda k: (k not in DB["kv"], DB["kv"].setdefault(k, "1"))[0]
S.kv_take = kv_take
S.touch_user = touch_user
S.get_user = lambda uid: DB["users"].get(uid)
S.add_purchase = add_purchase
S.ensure_purchase = lambda *a, **kw: None
S.get_purchase = lambda oc: (dict(DB["purchases"][oc]) if oc in DB["purchases"] else None)
S.purchases_of = purchases_of
S.mark_paid = lambda oc, amount_uah=None: None
S.mark_delivered = mark_delivered
S.mark_magnet = lambda uid: None
S.log_event = lambda uid, kind, payload=None: DB["events"].append((uid, kind, payload))
S.wipe_user = wipe_user
_UPD = [100]


def msg(text, uid, chat_type="private", chat_id=None, name="Гостя"):
    _UPD[0] += 1
    cid = uid if chat_id is None else chat_id
    return app.post("/sekret", json={"update_id": _UPD[0], "message": {
        "message_id": _UPD[0], "date": int(time.time()), "chat": {"id": cid, "type": chat_type},
        "from": {"id": uid, "first_name": name, "username": "u" + str(uid)}, "text": text}})


def tisne(data, uid):
    _UPD[0] += 1
    return app.post("/sekret", json={"update_id": _UPD[0], "callback_query": {
        "id": "cb" + str(_UPD[0]), "data": data, "from": {"id": uid, "first_name": "Гостя"},
        "message": {"message_id": 5, "chat": {"id": uid, "type": "private"}}}})


def to(chat):
    return [p for m, p in VYKLYKY if p.get("chat_id") == chat]


def z_knopkoyu(chat):
    return [p for p in to(chat) if p.get("reply_markup") == bot.PERSIST_KB]


def nosii(chat):
    return [p for p in to(chat) if p.get("text") == bot.PERSIST_LINE]


def inline(p):
    rm = p.get("reply_markup")
    return isinstance(rm, dict) and "inline_keyboard" in rm


def staff_bez_knopky():
    return not [p for m, p in VYKLYKY if p.get("chat_id") in (1, 7) and p.get("reply_markup") == bot.PERSIST_KB
                and p.get("text") != bot.PERSIST_LINE]


# 1. Нова людина, простий /start: вітання з інлайн-кнопкою, потім рядок-носій з кнопкою, рівно раз
VYKLYKY.clear()
msg("/start", 601)
t = to(601)
ok("новенька /start: вітання з інлайн-кнопкою магніту", t and inline(t[0])
   and any(b.get("callback_data") == "magnet" for r in t[0]["reply_markup"]["inline_keyboard"] for b in r))
ok("новенька /start: рядок-носій останнім, з постійною кнопкою", t and t[-1].get("text") == bot.PERSIST_LINE
   and t[-1].get("reply_markup") == bot.PERSIST_KB)
ok("новенька /start: кнопка рівно раз", len(z_knopkoyu(601)) == 1 and len(nosii(601)) == 1, str(len(z_knopkoyu(601))))
ok("новенька /start: прапорець pkb2 у kv", DB["kv"].get("pkb2:601") == "1" and bot.PKB_KEY == "pkb2")
ok("клавіатура: «Мої матеріали» і «Канал «для своїх»» в одному ряду",
   bot.PERSIST_KB["keyboard"] == [[{"text": "Мої матеріали"}, {"text": "Канал «для своїх»"}]]
   and bot.PERSIST_KB.get("is_persistent") is True)
ok("сповіщення «Новий у боті» персоналу є, кнопки в них нема",
   any((p.get("text") or "").startswith("Новий у боті") for p in to(1))
   and any((p.get("text") or "").startswith("Новий у боті") for p in to(7)) and staff_bez_knopky())

# 2. Та сама людина пише текст: прапорець є, рядка нема
VYKLYKY.clear()
msg("привіт", 601)
ok("з прапорцем: відповідь є, рядка-носія нема", to(601) and not nosii(601))

# 3. Повторний /start (після видалення чату кнопка зникає): знову рівно раз
VYKLYKY.clear()
msg("/start", 601)
ok("повторний /start: рядок-носій знову рівно раз", len(nosii(601)) == 1 and len(z_knopkoyu(601)) == 1)

# 4. Стара людина без прапорця (з бази до деплою) пише: рядок раз, далі тиша
DB["users"][602] = {"user_id": 602, "username": "u602", "first_name": "Стара"}
VYKLYKY.clear()
msg("добрий день", 602)
ok("стара людина: перше повідомлення дає рядок-носій раз", len(nosii(602)) == 1 and to(602)[-1].get("text") == bot.PERSIST_LINE)
VYKLYKY.clear()
msg("ще питання", 602)
ok("стара людина: друге повідомлення без рядка", to(602) and not nosii(602))

# 5. Стара людина тисне «Мої матеріали» знизу: така кнопка є і в старій клавіатурі, тож нову везе рядок-носій раз
DB["users"][603] = {"user_id": 603, "username": "u603", "first_name": "Стара2"}
VYKLYKY.clear()
msg("Мої матеріали", 603)
ok("натиснула «Мої матеріали»: відповідь і рядок-носій з новою клавіатурою раз", to(603) and len(nosii(603)) == 1
   and nosii(603)[0].get("reply_markup") == bot.PERSIST_KB)
ok("натиснула «Мої матеріали»: прапорець pkb2 у kv", DB["kv"].get("pkb2:603") == "1")
VYKLYKY.clear()
msg("Мої матеріали", 603)
ok("натиснула вдруге: рядка-носія нема", to(603) and not nosii(603))

# 5а. Стара клавіатура (прапорець pkb: до 13.10): наступне звернення міняє на нову рівно раз
DB["users"][620] = {"user_id": 620, "username": "u620", "first_name": "Зі старою"}
DB["kv"]["pkb:620"] = "1"
VYKLYKY.clear()
msg("добрий вечір", 620)
ok("стара клавіатура: рядок-носій з новою раз", len(nosii(620)) == 1 and nosii(620)[0]["reply_markup"] == bot.PERSIST_KB
   and DB["kv"].get("pkb2:620") == "1")
VYKLYKY.clear()
msg("ще одне", 620)
ok("стара клавіатура: далі без рядка", to(620) and not nosii(620))

# 5б. Кнопка каналу: рядок Іри з інлайн-кнопкою на запрошення knopka, подія, персоналу нічого
DB["users"][621] = {"user_id": 621, "username": "u621", "first_name": "Тисне канал"}
DB["events"].clear()
VYKLYKY.clear()
msg("Канал «для своїх»", 621)
t = to(621)
ok("кнопка каналу: одна відповідь, рядок Іри", len(t) == 1 and t[0].get("text") == bot.KANAL_BTN_TEXT
   and bot.KANAL_BTN_TEXT == "Підписуйтесь на мій тг канал, там розповідаю свою історію🫶🏻", str(t)[:200])
ok("кнопка каналу: інлайн-кнопка на запрошення knopka",
   t and t[0].get("reply_markup") == {"inline_keyboard": [[{"text": "Канал «для своїх»", "url": "https://t.me/+TESTknopka"}]]})
ok("кнопка каналу: подія kanal_btn", [e[1] for e in DB["events"] if e[0] == 621] == ["kanal_btn"], str(DB["events"]))
ok("кнопка каналу: персоналу нічого (ні пересилки, ні сповіщення)", not to(1) and not to(7))
ok("кнопка каналу: нова клавіатура вже є, прапорець pkb2 без рядка-носія", DB["kv"].get("pkb2:621") == "1" and not nosii(621))
VYKLYKY.clear()
msg("Канал «для своїх»", 7, name="Іра")
ok("Іра той самий текст: без постійної клавіатури", not z_knopkoyu(7) and "pkb2:7" not in DB["kv"])
_ku = bot.KANAL_KNOPKA_URL
bot.KANAL_KNOPKA_URL = ""
ok("без запрошення knopka: CHANNEL_URL", bot.kanal_btn_url() == "https://t.me/test_kanal")
bot.KANAL_KNOPKA_URL = _ku

# 6. Гостя МК: MK_HELLO без своєї клавіатури сам везе кнопку, рядка нема
VYKLYKY.clear()
msg("/start mk_" + KOD, 604)
t = to(604)
ok("гостя МК: MK_HELLO з постійною кнопкою", t and t[0].get("text") == bot.MK_HELLO
   and t[0].get("reply_markup") == bot.PERSIST_KB)
ok("гостя МК: рядка-носія нема", not nosii(604))
ok("гостя МК: сповіщення «МК: видано» без кнопки", any((p.get("text") or "").startswith("МК: видано") for p in to(1))
   and staff_bez_knopky())

# 7. Іра (IRA_ON вимкнений, як на живому): ні рядка, ні кнопки, ні прапорця
VYKLYKY.clear()
msg("/start", 7, name="Іра")
ok("Іра: /start без рядка і без постійної кнопки", to(7) and not nosii(7) and not z_knopkoyu(7))
ok("Іра: про свій /start «Новий у боті» нікому не йде",
   not [p for m, p in VYKLYKY if (p.get("text") or "").startswith("Новий у боті")])
VYKLYKY.clear()
msg("як справи", 7, name="Іра")
ok("Іра: текст без постійної кнопки", not z_knopkoyu(7) and "pkb2:7" not in DB["kv"])

# 8. Група: нічого
VYKLYKY.clear()
msg("/start", 605, chat_type="group", chat_id=-1005)
ok("група: без рядка і кнопки", not nosii(-1005) and not z_knopkoyu(-1005) and not nosii(605))

# 9. Натискання інлайн-кнопки людиною без прапорця: рядка нема (лише її повідомлення)
DB["users"][606] = {"user_id": 606, "username": "u606", "first_name": "Стара3"}
VYKLYKY.clear()
tisne("moi", 606)
ok("натискання інлайн-кнопки: рядка-носія нема", to(606) and not nosii(606) and "pkb2:606" not in DB["kv"])

# 10. Мітки з власними картками: retush, guide, kurs10, mk
for uid, tag in ((607, "retush"), (608, "guide"), (611, "kurs10"), (612, "mk")):
    VYKLYKY.clear()
    msg("/start " + tag, uid)
    t = to(uid)
    ok("мітка " + tag + ": рядок-носій останнім, рівно раз", t and t[-1].get("text") == bot.PERSIST_LINE
       and len(nosii(uid)) == 1, str([p.get("text", p.get("caption", ""))[:30] for p in t]))

# 11. Адмін пише сам: відповідь без клавіатури везе кнопку, сповіщення про себе без неї
VYKLYKY.clear()
msg("/start", 1, name="YR")
ok("адмін /start: рядок-носій раз, інших повідомлень з кнопкою нема",
   len(nosii(1)) == 1 and not [p for p in to(1) if p.get("reply_markup") == bot.PERSIST_KB
                               and p.get("text") != bot.PERSIST_LINE])
ok("адмін /start (він у NOTIFY_IDS): «Новий у боті» ні собі, ні Ірі",
   not [p for m, p in VYKLYKY if (p.get("text") or "").startswith("Новий у боті")])
VYKLYKY.clear()
msg("/nova", 1, name="YR")
msg("/start", 1, name="YR")
ok("ритуал /nova + /start адміна: Іра (7) нічого не отримала", not to(7) and len(nosii(1)) == 1, str(to(7))[:120])
VYKLYKY.clear()
msg("/mk", 1, name="YR")
ok("адмін /mk: відповідь без рядка-носія", to(1) and to(1)[-1]["text"].startswith("Посилання МК") and not nosii(1))

# 12. Без бази: у процесі рядок однаково не повторюється
_kg, _ks = S.kv_get, S.kv_set
S.kv_get, S.kv_set = (lambda k, d=None: None), (lambda k, v: None)
DB["users"][609] = {"user_id": 609, "username": "u609", "first_name": "Безбази"}
VYKLYKY.clear()
msg("раз", 609)
msg("два", 609)
ok("без бази: рядок-носій лише раз на процес", len(nosii(609)) == 1)
S.kv_get, S.kv_set = _kg, _ks

# 13. Відповідь зламалась: рядок сам по собі не йде
_sc = bot.send_card
bot.send_card = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("тест"))
VYKLYKY.clear()
msg("/start", 610)
ok("помилка у вітанні: рядка-носія нема", not nosii(610))
bot.send_card = _sc

# 14. /skyd стирає прапорець і памʼять процесу
r = app.get("/skyd/sekret?uid=601")
ok("/skyd: прапорець і памʼять стерто", r.status_code == 200 and "pkb2:601" not in DB["kv"]
   and 601 not in bot._pkb_done)
_calls = []
_q = store_mod.q
store_mod.q = lambda sql, args=(), fetch=None: _calls.append((sql, args)) or None
ORIG_WIPE(601)
store_mod.q = _q
ok("store.wipe_user: kv tag:, pkb: і pkb2: одним запитом", any("delete from kv" in s and "pkb:601" in a[0]
                                                                and "pkb2:601" in a[0] and "tag:601" in a[0]
                                                         for s, a in _calls), str(_calls[:1]))

# 15. Текст рядка той самий, що в боті при видачі курсу
ok("рядок-носій = речення з видачі курсу", bot.PERSIST_LINE in inspect.getsource(bot.give_course))

print("\nПАДІНЬ:", len(PADINNIA))
sys.exit(1 if PADINNIA else 0)
