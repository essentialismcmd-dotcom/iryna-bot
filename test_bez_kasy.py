#!/usr/bin/env python3
"""
Правки 29.09 (ревізія, З9 §6) БЕЗ мережі, бази і телеграма. Каси нема: PAY_URL порожній.

1. Тупик каси: жодної обіцянки реквізитів, оплати «скоро», «надішлю», кнопки «Гайд, 900 грн».
2. Канал після файлу: файл першим натиском, прохання про канал після нього.
3. Власники курсу: відповідь по суті, не шаблон «напишіть в інстаграм».
4. Лічильник стартів: /stats лише адміну.

Запуск:  python test_bez_kasy.py   (виходить 0, якщо все зелене)
"""

import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "MAGNET_URL": "MAGNIT",
                   "NOTIFY_IDS": "1", "CHANNEL_URL": "https://t.me/test_kanal"})
for k in ("DATABASE_URL", "PAY_URL", "COURSES_ON", "GUIDE_PRICE", "COURSE_PRICES", "TEST_MODE"):
    os.environ.pop(k, None)

import requests

VYKLYKY = []


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None):
    method = url.rsplit("/", 1)[-1]
    VYKLYKY.append((method, json or data or {}))
    if method == "getChatMember":
        return _R({"ok": True, "result": {"status": "left"}})
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import bot

app = bot.app.test_client()
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


def msg(text, uid=777):
    return app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": uid},
                    "from": {"id": uid, "first_name": "Т"}, "text": text}})


def cb(data, uid=777):
    return app.post("/sekret", json={"callback_query": {"id": "c", "data": data,
                    "from": {"id": uid, "first_name": "Т"}, "message": {"chat": {"id": uid}, "message_id": 5}}})


def komu(chat_id):
    return [p.get("text") or p.get("caption") or "" for m, p in VYKLYKY
            if m in ("sendMessage", "sendPhoto") and p.get("chat_id") == chat_id]


def knopky_vsi(chat_id):
    out = []
    for m, p in VYKLYKY:
        if p.get("chat_id") == chat_id and p.get("reply_markup"):
            for r in p["reply_markup"].get("inline_keyboard", []):
                out += [(b["text"], b.get("callback_data")) for b in r]
    return out


def knopky(chat_id):
    for m, p in reversed(VYKLYKY):
        if m in ("sendMessage", "sendPhoto") and p.get("chat_id") == chat_id and p.get("reply_markup"):
            return [b["text"] for r in p["reply_markup"]["inline_keyboard"] for b in r]
    return []


# ---- 1. Тупик каси
ok("каси нема: GUIDE_SALE вимкнений", bot.GUIDE_SALE is False)
VYKLYKY.clear()
for t in ("/start", "/start guide", "/start inst", "СВІТЛО", "ГАЙД", "світло", "МК", "ЗЙОМКА", "курс", "ретуш",
          "привіт як справи", "/moi"):
    msg(t, uid=555)
for d in ("magnet", "lock:check", "lock:free", "guide", "t1", "t2", "t3", "retush", "q:new", "q:pro",
          "k1", "k2", "k12", "mk", "mk:want", "moi", "my:guide", "noget:t1"):
    cb(d, uid=555)
bot.give_magnet(555)
vse = " ".join(komu(555)).lower()
zle = [w for w in ("реквізит", "скоро", "призначення платежу", "900", "гайд, ", "код ir",
                   "оплат") if w in vse]
ok("жодної обіцянки реквізитів, оплати, «скоро», «надішлю» про гроші, ціни гайда", not zle, str(zle))
ok("у коді бота нема рядка «Реквізити надішлю»", "Реквізити надішлю" not in open(bot.__file__, encoding="utf-8").read())
_kn = knopky_vsi(555)
ok("нема кнопок гайда й тарифів (guide, t1, t2, t3)", not [k for k in _kn if k[1] in ("guide", "t1", "t2", "t3")]
   and not [k for k in _kn if "гайд" in k[0].lower() and "грн" in k[0].lower()], str(_kn))
VYKLYKY.clear()
cb("t1", uid=556)
ok("стара кнопка «Гайд, 900 грн»: відповідь без реквізитів, з магнітом і каналом",
   komu(556) == [bot.PAUSED_TEXT] and knopky(556) == ["Забрати три схеми світла", "Канал «для своїх»"], str(komu(556)))
VYKLYKY.clear()
msg("СВІТЛО", uid=557)
ok("слово СВІТЛО з закріпу: те саме, магніт і канал", komu(557) == [bot.PAUSED_TEXT], str(komu(557)))
ok("без покупки нічого не записується: заявка не створюється, коду нема",
   not any("IR" in x and x.strip().startswith("IR") for x in komu(557)))
VYKLYKY.clear()
cb("magnet", uid=558)
ok("AFTER після файлу без рядка про кнопку гайда, якої нема",
   "Хочу повний гайд" not in " ".join(komu(558)) and "Хочете всі схеми" not in " ".join(komu(558)), str(komu(558)))
ok("порожні матеріали без слова про гайд", "гайд" not in bot.moi_empty().lower(), bot.moi_empty())

# із PAY_URL гайд повертається (перемикач працює в обидва боки)
bot.PAY_URL = "https://pay.test/jar"
bot.GUIDE_SALE = True
VYKLYKY.clear()
cb("guide", uid=559)
ok("PAY_URL заданий: гайд і тариф на місці", knopky(559) == [bot.TIERS["t1"]["btn"]], str(knopky(559)))
VYKLYKY.clear()
cb("t1", uid=559)
ok("PAY_URL заданий: код і кнопка оплати", any("Перейти до оплати" in x for x in knopky(559)) and "Реквізити" not in " ".join(komu(559)),
   str(komu(559)))
bot.PAY_URL = ""
bot.GUIDE_SALE = False

# ---- 2. Канал після файлу
VYKLYKY.clear()
cb("magnet", uid=600)
idx_file = [i for i, v in enumerate(VYKLYKY) if v[0] == "sendDocument"]
idx_txt = [i for i, v in enumerate(VYKLYKY) if v[0] in ("sendMessage", "sendPhoto") and v[1].get("chat_id") == 600]
ok("перший натиск магніта: файл", len(idx_file) == 1)
ok("прохання про канал після файлу, не перед", idx_file and idx_txt and idx_file[0] < idx_txt[0])
ok("у проханні кнопка каналу", "Канал «для своїх»" in knopky(600), str(knopky(600)))
ok("до файлу нічого не питаємо і нікого не перевіряємо", not [v for v in VYKLYKY if v[0] == "getChatMember"])

# ---- 3. Власники курсу
real_owned = bot.owned_keys
VYKLYKY.clear()
msg("Я вже купувала ваш курс, де дивитись?", uid=700)
t = komu(700)
ok("без покупки в базі: осмислена відповідь, не шаблон", t == [bot.OWNER_NONE] and bot.CLIENT_TEXT not in t, str(t))
ok("без покупки: не тупик, є кнопки магніта і каналу", knopky(700)[:1] == ["Забрати три схеми світла"], str(knopky(700)))
ok("текст відповіді без довгих тире і без цін", "—" not in bot.OWNER_NONE + bot.OWNER_HAS and "грн" not in bot.OWNER_NONE + bot.OWNER_HAS)
bot.owned_keys = lambda uid: {"k1"}
bot.COURSE_SECTIONS["k1"] = [("Урок 1", [("video", "V1")])]
VYKLYKY.clear()
msg("купив курс ретуші, як зайти", uid=701)
ok("є покупка курсу: ваш курс на місці і кнопки уроків", komu(701) == [bot.OWNER_HAS] and knopky(701) == ["Урок 1"],
   str(komu(701)) + str(knopky(701)))
bot.owned_keys = real_owned
VYKLYKY.clear()
msg("Скільки коштує зйомка?", uid=702)
ok("звичайний текст: як і було, шаблон про інстаграм", komu(702) == [bot.CLIENT_TEXT], str(komu(702)))
VYKLYKY.clear()
msg("Хочу купити гайд", uid=703)
ok("«купити» без слова курс не вважається власником", komu(703) == [bot.CLIENT_TEXT], str(komu(703)))
ok("адмін бачить текст людини, як і раніше", any("Повідомлення в боті" in x for x in komu(1)))

# ---- 4. Лічильник стартів
VYKLYKY.clear()
msg("/stats", uid=800)
ok("/stats від людини: службового нічого, звичайна відповідь", komu(800) == [bot.CLIENT_TEXT] and "Старти" not in " ".join(komu(800)), str(komu(800)))
ok("людині адмінові сповіщення не пішло зі статистикою", not any("Старти" in x for x in komu(1)))
VYKLYKY.clear()
msg("/stats", uid=1)
ok("/stats від адміна без бази: чесно каже, що бази нема", komu(1) == ["Бази нема (DATABASE_URL не заданий), рахувати нічого."], str(komu(1)))

bot.store.ON = True
REAL_STARTS = bot.store.starts_stats
bot.store.starts_stats = lambda skip: {"people": 12, "presses": 15, "day": 3, "week": 9, "magnet": 7,
                                       "tags": [{"tag": "inst", "people": 8, "presses": 10},
                                                {"tag": "chat", "people": 3, "presses": 3},
                                                {"tag": "без мітки", "people": 1, "presses": 2}]}
_SKIP = {}
_orig = bot.store.starts_stats
bot.store.starts_stats = lambda skip: (_SKIP.update(s=list(skip)) or _orig(skip))
VYKLYKY.clear()
msg("/stats", uid=1)
tx = komu(1)[0] if komu(1) else ""
ok("/stats від адміна: люди, натиски, добу, тиждень, магніт", "Людей: 12, натисків /start: 15" in tx and "За добу: 3, за 7 днів: 9" in tx
   and "Отримали магніт: 7" in tx, tx)
ok("/stats: розбивка inst і chat", "inst: 8 / 10" in tx and "chat: 3 / 3" in tx and "без мітки: 1 / 2" in tx, tx)
ok("/stats: адмін і Іра виключені з підрахунку", _SKIP.get("s") == [1] or set(_SKIP.get("s", [])) >= {1}, str(_SKIP))
r = app.get("/stats/sekret")
ok("HTTP /stats/<S> віддає те саме", r.status_code == 200 and "inst: 8 / 10" in r.get_data(as_text=True))
ok("HTTP /stats з чужим секретом 404", app.get("/stats/nope").status_code == 404)
bot.store.ON = False


# ---- 5. Курси без каси: COURSES_ON=1, PAY_URL порожній (п. 1 вердикту 29.09)
bot.COURSES_ON = True
bot.PAY_URL = ""
bot.GUIDE_SALE = False
ok("COURSES_ON=1 без PAY_URL: продажу курсів нема", bot.courses_sale() is False)
VYKLYKY.clear()
UID = 900
for t in ("/start", "/start guide", "/start inst", "/start курс", "СВІТЛО", "ГАЙД", "МК", "ЗЙОМКА",
          "КУРС", "курс", "ретуш", "РЕТУШ", "привіт як справи", "хочу курс ретуші", "/moi", "Мої матеріали"):
    msg(t, uid=UID)
for d in ("magnet", "guide", "t1", "t2", "t3", "retush", "q:new", "q:pro", "k1", "k2", "k12", "mk", "moi",
          "my:guide", "noget:t1", "lock:check", "lock:free"):
    cb(d, uid=UID)
bot.give_magnet(UID)
bot.give_guide(UID, "t1")   # прямий виклик: без каси курс після гайда теж не пропонується
_txt = "\n".join(komu(UID))
_kn = knopky_vsi(UID)
_kn_txt = " ".join(b[0] for b in _kn)
_ceny = [str(bot._K1), str(bot._K2), str(bot._K12), str(bot._G), str(bot._T2), str(bot._T3)]
ok("жодного «грн» ні в тексті, ні на кнопці", "грн" not in _txt.lower() and "грн" not in _kn_txt.lower(), _kn_txt)
ok("жодної ціни числом (3200, 1900, 4500, 900...) ні в тексті, ні на кнопці",
   not [c for c in _ceny if c in _txt or c in _kn_txt], str(_ceny))
ok("нема підводок RETUSH_INTRO/NEW/PRO і пакета",
   not any(x in _txt for x in (bot.RETUSH_INTRO, bot.RETUSH_NEW, bot.RETUSH_PRO, bot.RETUSH_BUNDLE)))
ok("нема кнопок «Курс ретуші», рівнів і покупки курсів (retush, q:*, k1, k2, k12)",
   not [b for b in _kn if b[1] in ("retush", "q:new", "q:pro", "k1", "k2", "k12")]
   and "Курс ретуші" not in _kn_txt and "Перший курс" not in _kn_txt and "Обидва" not in _kn_txt, str(_kn))
ok("нема кнопок оплати, гайда і тарифів", not [b for b in _kn if b[1] in ("guide", "t1", "t2", "t3") or "оплат" in b[0].lower()]
   and "Перейти до оплати" not in _kn_txt, str(_kn))
ok("жодного запису заявки: коду IR... нема в текстах", not any(x.strip().startswith("IR") for x in komu(UID)))
VYKLYKY.clear()
for d in ("retush", "q:new", "q:pro", "k1", "k2", "k12"):
    cb(d, uid=901)
ok("старі кнопки курсів: усі шість дають RETUSH_SOON", komu(901) == [bot.RETUSH_SOON] * 6, str(komu(901)))
VYKLYKY.clear()
msg("КУРС", uid=902)
msg("ретуш", uid=902)
ok("слова КУРС і РЕТУШ: RETUSH_SOON", komu(902) == [bot.RETUSH_SOON] * 2, str(komu(902)))
ok("moi_empty без цін і слова про курс", "курс" not in bot.moi_empty().lower() and "грн" not in bot.moi_empty())
# доступ до вже куплених уроків від каси не залежить
bot.owned_keys = lambda uid: {"k1"}
bot.COURSE_SECTIONS["k1"] = [("Урок 1", [("video", "V1")])]
VYKLYKY.clear()
msg("/moi", uid=903)
ok("COURSES_ON=1 без каси: /moi власнику показує уроки", komu(903) == [bot.MOI_TEXT] and knopky(903) == ["Урок 1"],
   str(komu(903)) + str(knopky(903)))
VYKLYKY.clear()
cb("les:k1:0", uid=903)
ok("COURSES_ON=1 без каси: урок віддається", any(m in ("sendVideo", "sendDocument") for m, _ in VYKLYKY), str([m for m, _ in VYKLYKY]))
bot.owned_keys = real_owned
# із касою і COURSES_ON продаж повертається (перемикач працює в обидва боки)
bot.PAY_URL = "https://pay.test/jar"
bot.GUIDE_SALE = True
ok("COURSES_ON=1 і PAY_URL: courses_sale увімкнений", bot.courses_sale() is True)
VYKLYKY.clear()
cb("retush", uid=904)
ok("з касою: кнопки рівнів на місці", knopky(904) == ["Тільки починаю", "Вже працюю у фотошопі"], str(knopky(904)))
bot.PAY_URL = ""
bot.GUIDE_SALE = False
bot.COURSES_ON = False

# ---- 6. Власники: розпізнавання (п. 4)
_TAK = ["я вже купила курс", "у мене вже є курс", "я вже проходила ваш курс", "купувала у вас курс",
        "в мене є ваш курс", "у меня уже есть курс", "купив курс ретуші, як зайти"]
_NI = ["я вже хочу курс", "вже хочу купити курс", "вже можна купити курс?", "коли вже буде курс",
       "чи вже є курс?", "хочу курс ретуші"]
for t in _TAK:
    ok("власник: «" + t + "»", bool(bot.OWNER_RE.search(t.lower())))
for t in _NI:
    ok("не власник: «" + t + "»", not bot.OWNER_RE.search(t.lower()))
VYKLYKY.clear()
msg("я вже хочу курс", uid=910)
msg("коли вже буде курс", uid=910)
ok("охочий купити не отримує «покупки не бачу»", bot.OWNER_NONE not in komu(910) and bot.OWNER_HAS not in komu(910), str(komu(910)))
# покупка є, а кнопок уроків нема (файли курсу не залиті): «не бачу» не кажемо
bot.owned_keys = lambda uid: {"k1"}
bot.COURSE_SECTIONS["k1"] = []
VYKLYKY.clear()
msg("я вже купила курс", uid=911)
ok("покупка є, уроків нема: не «покупки не бачу»", komu(911) and bot.OWNER_NONE not in komu(911), str(komu(911)))
# власник лише гайда
bot.owned_keys = lambda uid: {"t1"}
VYKLYKY.clear()
msg("я вже купила курс", uid=912)
ok("власник лише гайда: не «покупки не бачу», кнопка гайда", bot.OWNER_NONE not in komu(912) and "Гайд «Світло»" in knopky(912),
   str(komu(912)) + str(knopky(912)))
bot.owned_keys = real_owned

# ---- 7. /stats: екранування, ліміти, збій бази (п. 6)
bot.store.ON = True
_evil = "<script>alert(1)</script>"
bot.store.starts_stats = lambda skip: {"people": 1, "presses": 1, "day": 0, "week": 0, "magnet": 0,
                                       "tags": [{"tag": _evil, "people": 1, "presses": 1}]}
r = app.get("/stats/sekret")
_h = r.get_data(as_text=True)
ok("HTML /stats: мітка <script> екранована", "<script>" not in _h and "&lt;script&gt;" in _h, _h[:200])
ok("HTML /stats: обгортка <pre> ціла", _h.startswith("<pre>") and _h.endswith("</pre>"))
_many = [{"tag": "m%03d" % i, "people": 200 - i, "presses": 300 - i} for i in range(100)]
bot.store.starts_stats = lambda skip: {"people": 500, "presses": 900, "day": 1, "week": 2, "magnet": 3, "tags": _many}
tx = bot.starts_text()
_rows = [l for l in tx.split("\n") if l.startswith("  m")]
ok("100 міток: у відповіді рівно 30 і перші за кількістю", len(_rows) == bot.STATS_TAGS_MAX and _rows[0].startswith("  m000")
   and _rows[-1].startswith("  m029"), str(len(_rows)))
_sum_p = sum(r["people"] for r in _many[30:])
_sum_x = sum(r["presses"] for r in _many[30:])
ok("100 міток: решта одним рядком «інші»", ("  інші (70 міток): %d / %d" % (_sum_p, _sum_x)) in tx, tx[-120:])
ok("100 міток: довжина ≤ 4000", len(tx) <= 4000, str(len(tx)))
_m = bot.STATS_TEXT_MAX
bot.STATS_TEXT_MAX = 300
ok("обрізка до ліміту працює (ліміт 300)", len(bot.starts_text()) <= 300)
bot.STATS_TEXT_MAX = _m
bot.store.starts_stats = lambda skip: {"people": 1, "presses": 1, "day": 0, "week": 0, "magnet": 0,
                                       "tags": [{"tag": "a\nb\n<i>", "people": 1, "presses": 1}]}
ok("мітка з переносом рядка йде одним рядком", "  a b <i>: 1 / 1" in bot.starts_text())
bot.store.starts_stats = lambda skip: {"people": 500, "presses": 900, "day": 1, "week": 2, "magnet": 3, "tags": _many}
VYKLYKY.clear()
msg("/stats", uid=1)
ok("/stats у Telegram: одне повідомлення ≤ 4000", len(komu(1)) == 1 and len(komu(1)[0]) <= 4000, str([len(x) for x in komu(1)]))
# збій бази
bot.store.starts_stats = lambda skip: None
ok("збій бази (немає відповіді): окремий рядок, не «стартів ще нема»",
   bot.starts_text() == "База не відповіла, спробуйте ще раз.")
# збій лише запиту міток: справжня starts_stats з q(), що на «all» дає []
_q = bot.store.q


def _fake_q(sql, args=(), fetch=None):
    if "group by 1" in sql:
        return []            # збій запиту міток: q() дає [] замість рядків
    if "count(distinct user_id) as people" in sql:
        return {"people": 5, "presses": 7, "day": 1, "week": 2}
    return {"n": 3}


bot.store.q = _fake_q
bot.store.starts_stats = REAL_STARTS
tx = bot.starts_text()
ok("збій запиту міток при наявних стартах: «база не відповіла», не «стартів ще нема»",
   "стартів ще нема" not in tx and "розбивка: база не відповіла" in tx, tx)


def _fake_q0(sql, args=(), fetch=None):
    if "group by 1" in sql:
        return []
    if "count(distinct user_id) as people" in sql:
        return {"people": 0, "presses": 0, "day": 0, "week": 0}
    return {"n": 0}


bot.store.q = _fake_q0
tx = bot.starts_text()
ok("справді нема стартів: «стартів ще нема»", "стартів ще нема" in tx and "база не відповіла" not in tx, tx)
bot.store.q = _q
bot.store.ON = False

print("\nПАДІНЬ:", len(PADINNIA))
sys.exit(1 if PADINNIA else 0)
