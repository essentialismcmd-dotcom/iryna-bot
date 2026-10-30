#!/usr/bin/env python3
"""31.10, слово Yaro «перебудувати все»: кожен екран веде в особисті @iryna_rul_studio з початою фразою
(людині лишається дописати слово); курс з-під подарунка і «Ціна і оплата» під вітриною лише за прапорцями
KURS_PID_PODARUNKOM / KURS_TSINA_KNOPKA; голос Іри без «помічниці»; події dm_offer / dm_written,
GET /mist/<key>/shliakhy для ранкового розбору. Без мережі, бази і месенджера.
Запуск: python test_rozmova_31.py (0, якщо все зелене)."""
import os, sys, json
from urllib.parse import urlparse, parse_qs
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "NO_THREADS": "1",
                   "COURSES_ON": "1", "COURSE_BUNDLE_ONLY": "1", "COURSE_PRICES": "3200,1900,3300",
                   "PAY_URL": "https://pay.test/jar", "NOTIFY_IDS": "1", "GUIDE_FILE_ID": "GUIDE", "MAGNET_URL": "MAGNIT",
                   "CHANNEL_URL": "https://t.me/test_kanal", "MIST_KEY": "kliuch-test", "GIFT_FOR_SUB": "1"})
for k in ("DATABASE_URL", "KURS_PID_PODARUNKOM", "KURS_TSINA_KNOPKA", "IRA_DM_URL", "TEST_MODE"):
    os.environ.pop(k, None)
import requests

VYKLYKY = []


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


STATUS = {"v": "member"}        # відповідь getChatMember: «left» до підписки, «member» після


def fake_post(url, json=None, data=None, files=None, timeout=None):
    method = url.rsplit("/", 1)[-1]
    VYKLYKY.append((method, json or data or {}))
    if method == "getChatMember":
        return _R({"ok": True, "result": {"status": STATUS["v"]}})
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import bot, store

KV, EV = {}, []
store.kv_get = lambda k, default=None: KV.get(k, default)
store.kv_set = lambda k, v: KV.__setitem__(k, v)
store.kv_claim = lambda k: (k not in KV) and (KV.__setitem__(k, "1") or True)
store.kv_del = lambda k: KV.pop(k, None)
store.log_event = lambda uid, kind, payload=None: EV.append((uid, kind, payload))
store.session_begin = lambda: None
store.session_end = lambda: None
store.get_user = lambda uid: {"id": uid, "first_name": "Т"}
store.mark_magnet = lambda uid: None
bot.bg = lambda fn, *a, **k: fn(*a, **k)
bot.notify = lambda *a, **k: None
bot.notify_lead = lambda *a, **k: None
bot.lead_once = lambda uid, what: True
bot.magnet_ref = lambda: "MAGNET"
bot.send_preset_files = lambda chat_id, keys: True
bot.send_kurs_album = lambda chat_id: None
bot.kabinet_mist.push_user = lambda uid: None
app = bot.app.test_client()
PADINNIA = []
METODY = ("sendMessage", "sendPhoto", "sendDocument")


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + str(dovidka)[:400] if dovidka and not umova else ""))
    if not umova:
        PADINNIA.append(nazva)


def names(kb):
    return [b["text"] for r in (kb or {}).get("inline_keyboard", []) for b in r]


def urls(kb):
    return [b.get("url", "") for r in (kb or {}).get("inline_keyboard", []) for b in r]


def pered_z(url):
    return parse_qs(urlparse(url).query).get("text", [""])[0]


def msg(text, uid=777):
    return app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": uid},
                    "from": {"id": uid, "first_name": "Т"}, "text": text}})


def cb(data, uid=777):
    return app.post("/sekret", json={"callback_query": {"id": "c", "data": data,
                    "from": {"id": uid, "first_name": "Т"}, "message": {"chat": {"id": uid}, "message_id": 5}}})


def ostannia(chat_id, methods=METODY):
    for m, p in reversed(VYKLYKY):
        if m in methods and p.get("chat_id") == chat_id and p.get("reply_markup"):
            kb = p["reply_markup"]
            return json.loads(kb) if isinstance(kb, str) else kb
    return {}


def teksty(chat_id):
    return [p.get("text") or p.get("caption") or "" for m, p in VYKLYKY if m in METODY and p.get("chat_id") == chat_id]


# 1. Посилання і початі фрази
ok("dm_url без фрази: чисте посилання", bot.dm_url("") == bot.IRA_DM_URL)
ok("dm_url з фразою: ?text=, фраза ціла", pered_z(bot.dm_url("Привіт! Знімаю ")) == "Привіт! Знімаю ")
ok("pered_vilnyi: слова людини, пробіли стиснуто", bot.pered_vilnyi("  хочу   курс\nретуші ") == "хочу курс ретуші")
ok("pered_vilnyi: команду не переносимо", bot.pered_vilnyi("/start preset") == "")
ok("pered_vilnyi: до 300 знаків", len(bot.pered_vilnyi("а" * 500)) == 300)
ok("початі фрази закінчуються так, щоб людина дописала слово",
   all(p.endswith((" ", ": ")) for p in (bot.PERED_PRESET, bot.PERED_SHEMY, bot.PERED_SHEMA4, bot.PERED_HAJD, bot.PERED_KURS,
                                          bot.PERED_KURS_TSINA, bot.PERED_MK, bot.PERED_TSINA, bot.PERED_ZYOMKA, bot.PERED_MOI,
                                          bot.PERED_PRESET_MORE, bot.TOUCH_D2_PERSHE, bot.HAJD_PERSHE)))
ok("store: rozmova_stats(days) окремо від dm_stats() асистентки",
   store.rozmova_stats.__code__.co_varnames[:1] == ("days",) and store.dm_stats.__code__.co_argcount == 0)

# 2. Після подарунка (after_kb)
EV.clear()
kb = bot.after_kb(bot.PERED_PRESET.format(nazva="Єва"), "preset", 5)
ok("після пресета: перша кнопка «Показати кадр Ірі» з початою фразою",
   names(kb)[0] == "Показати кадр Ірі" and pered_z(urls(kb)[0]) == "Привіт, Іро! Пресет «Єва» взяла. Знімаю ", (names(kb), urls(kb)))
ok("після пресета: гайд є, курсу і каналу нема (KURS_PID_PODARUNKOM=0)",
   "Хочу повний гайд «Світло»" in names(kb) and "Курс ретуші" not in names(kb) and "Канал «для своїх»" not in names(kb), names(kb))
ok("після пресета: подія dm_offer з екраном", (5, "dm_offer", {"ekran": "preset"}) in EV, EV)
bot.KURS_PID_PODARUNKOM = True
ok("KURS_PID_PODARUNKOM=1 повертає курс під подарунок", "Курс ретуші" in names(bot.after_kb(bot.PERED_SHEMA4, "shema4", 5)))
bot.KURS_PID_PODARUNKOM = False
kb = bot.after_kb(bot.PERED_SHEMY, "magnet", 5, kanal=True)
ok("give_magnet (файл без підписки): канал є, бо текст AFTER його просить",
   names(kb)[0] == "Показати кадр Ірі" and names(kb)[-1] == "Канал «для своїх»", names(kb))
ok("PRESET_AFTER: без слова «курс», кличе показати кадр або написати, на чому знімає",
   "курс" not in bot.PRESET_AFTER.lower() and "покажіть мені" in bot.PRESET_AFTER.lower()
   and "на чому і де знімаєте" in bot.PRESET_AFTER.lower(), bot.PRESET_AFTER)
ok("SHEMA4_AFTER і GIFT_SUB: той самий привід написати",
   "покажіть мені кадр" in bot.SHEMA4_AFTER.lower() and "покажіть мені кадр" in bot.GIFT_SUB.lower()
   and "на чому і де знімаєте" in bot.GIFT_SUB.lower())

# 3. Пресет з реклами через вебхук: /start preset → «Я підписалась» → файл, після нього кнопки
VYKLYKY.clear(); EV.clear(); KV.clear()
STATUS["v"] = "left"
msg("/start preset", 10)
ok("вхід з реклами без підписки: ворота з каналом і «Я підписалась», файла ще нема",
   names(ostannia(10)) == ["Канал «для своїх»", "Я підписалась"] and not [m for m, _ in VYKLYKY if m == "sendDocument"], names(ostannia(10)))
STATUS["v"] = "member"
cb("sub:check", 10)
kb = ostannia(10)
ok("пресет після підписки: кадр Ірі з назвою пресета, гайд, ще пресети; курсу нема",
   names(kb)[:1] == ["Показати кадр Ірі"] and "Колір 1" in pered_z(urls(kb)[0]) and names(kb)[-1] == "Хочу ще пресети"
   and "Курс ретуші" not in names(kb), (names(kb), urls(kb)))
ok("пресет: тексти після файла без «курс»", not any("курс" in t.lower() for t in teksty(10)), teksty(10))
ok("пресет: подія dm_offer preset", (10, "dm_offer", {"ekran": "preset"}) in EV, EV)

# 4. Три схеми (give_gift): кадр Ірі, гайд, канал; курсу нема
VYKLYKY.clear(); EV.clear(); KV.clear()
ok("три схеми видано", bot.give_gift(11, bot.GIFT_SUB) is True)
kb = ostannia(11, ("sendDocument",))
ok("три схеми: кадр Ірі першою з фразою, гайд, канал; курсу нема",
   names(kb)[:1] == ["Показати кадр Ірі"] and pered_z(urls(kb)[0]) == bot.PERED_SHEMY and "Хочу повний гайд «Світло»" in names(kb)
   and "Канал «для своїх»" in names(kb) and "Курс ретуші" not in names(kb), (names(kb), urls(kb)))
ok("три схеми: подія dm_offer shemy", (11, "dm_offer", {"ekran": "shemy"}) in EV, EV)

# 5. Гайд: картка з ціною і «Спитати перед покупкою»; після покупки голос Іри
kb = bot.tiers_kb()
ok("картка гайда: тариф і «Спитати перед покупкою» з початою фразою",
   names(kb)[-1] == "Спитати перед покупкою" and pered_z(urls(kb)[-1]) == bot.PERED_HAJD, names(kb))
ok("вступ гайда рахує лише тарифи (одна кнопка, не «Три варіанти»)", bot.guide_intro(kb) == bot.GUIDE_INTRO_HEAD + bot.GUIDE_INTRO_ONE)
VYKLYKY.clear(); EV.clear()
bot.give_guide(12, "t1")
kb = ostannia(12)
ok("після гайда: «Написати Ірі» з фразою покупця і канал",
   names(kb)[:1] == ["Написати Ірі"] and pered_z(urls(kb)[0]) == bot.HAJD_PERSHE and "Канал «для своїх»" in names(kb), (names(kb), urls(kb)))
ok("гайд: голос Іри, без «помічниці», відповідає 24/7",
   "помічниц" not in (bot.HAJD_PIDTRYMKA + bot.TOUCH_D2_HAJD + bot.CLIENT_TEXT + bot.ASK_KURS).lower()
   and "@iryna_rul_studio" in bot.HAJD_PIDTRYMKA and "24/7" in bot.HAJD_PIDTRYMKA)
ok("після гайда: подія dm_offer hajd", (12, "dm_offer", {"ekran": "hajd"}) in EV, EV)

# 6. Курс: вітрина без ціни, одна кнопка; «Ціна і оплата» лише з прапорцем
kb = bot.kurs_vitryna_kb()
ok("вітрина курсу: одна кнопка «Написати Ірі» з фразою курсу", names(kb) == ["Написати Ірі"] and pered_z(urls(kb)[0]) == bot.PERED_KURS, names(kb))
bot.KURS_TSINA_KNOPKA = True
ok("KURS_TSINA_KNOPKA=1: «Ціна і оплата» другою", names(bot.kurs_vitryna_kb()) == ["Написати Ірі", "Ціна і оплата"])
bot.KURS_TSINA_KNOPKA = False

# 7. Слова і вільний текст: кнопка несе слова людини
VYKLYKY.clear(); EV.clear()
msg("Дякую, все прийшло, дуже гарно", 13)
kb = ostannia(13)
ok("вільний текст: CLIENT_TEXT і кнопка з її ж словами",
   bot.CLIENT_TEXT in teksty(13) and names(kb)[:1] == ["Написати Ірі"] and pered_z(urls(kb)[0]) == "Дякую, все прийшло, дуже гарно",
   (teksty(13), names(kb), urls(kb)))
ok("вільний текст: подія dm_offer tekst", (13, "dm_offer", {"ekran": "tekst"}) in EV, EV)
VYKLYKY.clear()
msg("ЗЙОМКА", 14)
kb = ostannia(14)
ok("слово «зйомка»: в особисті з фразою про зйомку", names(kb)[:1] == ["Написати Ірі"] and pered_z(urls(kb)[0]) == bot.PERED_ZYOMKA,
   (teksty(14), names(kb), urls(kb)))

# 8. Мої матеріали як платформа
bot.lessons_kb = lambda uid: {"inline_keyboard": [[{"text": "Урок 1", "callback_data": "les:k1:0"}]]} if uid == 5 else None
bot.free_owned = lambda uid: ["shemy"] if uid == 5 else []
bot.owned_keys = lambda uid, real=False: {"k1", "k2"} if uid == 5 else set()
n = names(bot.moi_kb(5))
ok("мої матеріали: уроки, безкоштовне, гайд (ще нема), чат з Ірою; куплений курс не пропонуємо",
   n[0] == "Урок 1" and "Три схеми світла" in n and "Хочу повний гайд «Світло»" in n and "Курс ретуші" not in n
   and n[-1] == "Написати Ірі" and pered_z(urls(bot.moi_kb(5))[-1]) == bot.PERED_MOI, n)
ok("порожні матеріали: None (далі empty_kb)", bot.moi_kb(6) is None)
bot.owned_keys = lambda uid, real=False: {"t1"} if uid == 5 else set()
n = names(bot.moi_kb(5))
ok("власник гайда: курс є, гайда нема", "Курс ретуші" in n and "Хочу повний гайд «Світло»" not in n, n)
ok("empty_kb: остання кнопка «Написати Ірі»", names(bot.empty_kb(6))[-1] == "Написати Ірі", names(bot.empty_kb(6)))

# 9. Міст: розмова пише dm_written; /mist/shliakhy віддає шлях кожної людини
KV.clear(); EV.clear()
r = app.post("/mist/kliuch-test/rozmova", json={"id": 5, "ekran": "preset", "text": "Привіт, Іро! Пресет «Єва» взяла. Знімаю на Canon"})
ok("/mist/rozmova: kv rozmova: і подія dm_written з екраном і словами",
   r.status_code == 200 and KV.get("rozmova:5")
   and (5, "dm_written", {"ekran": "preset", "text": "Привіт, Іро! Пресет «Єва» взяла. Знімаю на Canon"}) in EV, (r.status_code, KV, EV))
ok("/mist/rozmova без екрана (стара асистентка): подія з порожнім екраном",
   app.post("/mist/kliuch-test/rozmova", json={"id": 6}).status_code == 200 and (6, "dm_written", {"ekran": "", "text": ""}) in EV, EV)
ok("/mist/rozmova: чужий ключ 404", app.post("/mist/zlyi/rozmova", json={"id": 5}).status_code == 404)
store.shliakhy_users = lambda days=14, limit=300: [
    {"user_id": 5, "username": "ann", "first_name": "Анна", "last_name": None, "source_tag": "preset",
     "created_at": "2026-10-30", "last_at": "2026-10-31", "ekrany": ["preset"]},
    {"user_id": 1, "username": "admin", "ekrany": []}]
store.rozmova_stats = lambda days=7: {"offer": 10, "offer_rozmova": 3, "kurs": 4, "kurs_rozmova": 1}
bot.shliakh = lambda uid, most=8: "пресет → кнопка в особисті"
bot.owned_keys = lambda uid, real=False: set()
r = app.get("/mist/kliuch-test/shliakhy?days=7")
j = r.get_json() or {}
ok("/mist/shliakhy: люди без персоналу, розмова з kv, мітка, імʼя, підсумок",
   r.status_code == 200 and j.get("days") == 7 and [p["uid"] for p in j.get("liudy", [])] == [5]
   and j["liudy"][0]["rozmova"] is True and j["liudy"][0]["mitka"] == "preset" and j["liudy"][0]["imia"] == "Анна"
   and j["pidsumok"]["offer"] == 10, j)
ok("/mist/shliakhy: чужий ключ 404", app.get("/mist/zlyi/shliakhy").status_code == 404)
ok("SHLIAKH_KINDS: нові події людською мовою", all(k in bot.SHLIAKH_KINDS for k in ("dm_written", "kurs_vitryna", "tier_pick")))

print()
if PADINNIA:
    print("ПАДІННЯ: " + ", ".join(PADINNIA))
sys.exit(1 if PADINNIA else 0)
