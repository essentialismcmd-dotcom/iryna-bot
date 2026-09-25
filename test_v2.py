#!/usr/bin/env python3
"""
Перевірка змін v2 (25.09) БЕЗ мережі, бази і телеграма: ціни t2/t3, слова
з закріпу каналу (СВІТЛО, МК, ЗЙОМКА, КУРС), заявка на МК, режим «тільки
пакет», заливка з роллю і версії файлів. Запуск: python test_v2.py
"""
import os, sys, io

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "NOTIFY_IDS": "1",
                   "LEAD_IDS": "1,2", "CHANNEL_URL": "https://t.me/test_kanal",
                   "COURSES_ON": "1"})
for k in ("DATABASE_URL", "GUIDE_PRICE", "GUIDE_TIER_PRICES", "COURSE_PRICES", "COURSE_BUNDLE_ONLY"):
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
    if method == "sendDocument" and files:
        return _R({"ok": True, "result": {"document": {"file_id": "NEWFILE"}}})
    if method == "getFile":
        return _R({"ok": True, "result": {"file_size": 1000}})
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
    return [p.get("text", "") for m, p in VYKLYKY if m == "sendMessage" and p.get("chat_id") == chat_id]


def knopky(chat_id=777):
    for m, p in reversed(VYKLYKY):
        if m == "sendMessage" and p.get("chat_id") == chat_id and p.get("reply_markup"):
            return [b["text"] for r in p["reply_markup"]["inline_keyboard"] for b in r]
    return []


# 1. t2 більше не дорівнює t1
ok("типові ціни: 900 / 1200 / 1900", (bot._G, bot._T2, bot._T3) == (900, 1200, 1900), str((bot._G, bot._T2, bot._T3)))
ok("t2 дорожчий за гайд", bot.TIERS["t2"]["uah"] > bot.TIERS["t1"]["uah"] and "1200 грн" in bot.TIERS["t2"]["btn"])
ok("t3 дорожчий за t2", bot.TIERS["t3"]["uah"] > bot.TIERS["t2"]["uah"])
ok("GUIDE_TIER_PRICES зі змінної", bot._tier_prices("1300,2000", 900) == [1300, 2000])
ok("криві ціни тарифів відкидаються", bot._tier_prices("800,2000", 900) == [1200, 1900]
   and bot._tier_prices("abc", 650) == [950, 1650])
ok("банка знає ціну t2", bot.PRODUCTS["t2"]["uah"] == 1200)

# 2. Слова з закріпу каналу
ok("слова розпізнаються", [bot.keyword(x) for x in ("СВІТЛО", "мк", "Зйомка!", "курс", "привіт", "хочу світло")]
   == ["guide", "mk", "shoot", "retush", None, None])
VYKLYKY.clear(); msg("СВІТЛО")
ok("СВІТЛО веде на гайд", any("Повний гайд" in x for x in komu(777)) and knopky() == ["Гайд, 900 грн"], str(knopky()))
ok("одна кнопка: без «Три варіанти», заклик до кнопки",
   not any("Три варіанти" in x for x in komu(777)) and any(bot.GUIDE_INTRO_ONE in x for x in komu(777)))
VYKLYKY.clear(); cb("guide")
ok("кнопка гайда: той самий текст на одну кнопку",
   any(bot.GUIDE_INTRO_ONE in x for x in komu(777)) and not any("Три варіанти" in x for x in komu(777)))
_tiers = bot.GUIDE_TIERS[:]
bot.GUIDE_TIERS[:] = ["t1", "t2", "t3"]
VYKLYKY.clear(); msg("СВІТЛО")
ok("три тарифи: «Три варіанти» і три кнопки",
   any("Три варіанти, оберіть свій." in x for x in komu(777)) and len(knopky()) == 3, str(knopky()))
bot.GUIDE_TIERS[:] = _tiers
VYKLYKY.clear(); msg("МК")
ok("МК: текст і кнопка заявки", any("майстер-клас" in x for x in komu(777)) and knopky() == ["Хочу на майстер-клас"])
ok("МК без ціни в тексті", not any("$" in x or "грн" in x for x in komu(777)))
VYKLYKY.clear(); cb("mk:want")
ok("заявка на МК: людині подяка", any("Записала" in x for x in komu(777)))
ok("заявка на МК летить у LEAD_IDS", any("ЗАЯВКА НА МК" in x for x in komu(1)) and any("ЗАЯВКА НА МК" in x for x in komu(2)))
VYKLYKY.clear(); msg("зйомка")
ok("ЗЙОМКА: інстаграм і сигнал", any("інстаграм" in x for x in komu(777)) and any("ЗЙОМКУ" in x for x in komu(2)))
VYKLYKY.clear(); msg("просто питання про щось")
ok("звичайний текст як раніше", any("Прийняла" in x for x in komu(777)))

# 3. Режим «тільки пакет»
VYKLYKY.clear(); cb("retush")
ok("без режиму: кваліфікатор", knopky() == ["Тільки починаю", "Вже працюю у фотошопі"])
bot.COURSE_BUNDLE_ONLY = True
VYKLYKY.clear(); cb("retush")
ok("тільки пакет: одна кнопка", knopky() == ["Обидва курси, 4500 грн"], str(knopky()))
VYKLYKY.clear(); msg("курс")
ok("слово КУРС теж пакет", knopky() == ["Обидва курси, 4500 грн"])
bot.COURSE_BUNDLE_ONLY = False

# 3б. Старі курси зняті з продажу (25.09): COURSES_ON вимкнений
bot.COURSES_ON = False
VYKLYKY.clear(); msg("/start guide")
ok("вимкнено: ?start=guide без кнопки курсу", "Курс ретуші" not in knopky() and not any("два записані курси" in x for x in komu(777)), str(knopky()))
_kb = [b["text"] for r in bot.after_kb()["inline_keyboard"] for b in r]
ok("вимкнено: після магніта нема кнопки курсу", "Курс ретуші" not in _kb and "Хочу повний гайд «Світло»" in _kb, str(_kb))
for d in ("retush", "q:new", "k1", "k2", "k12"):
    VYKLYKY.clear(); cb(d)
    ok("вимкнено: " + d + " веде на гайд і канал, без заявки",
       knopky() == ["Хочу повний гайд «Світло»", "Канал «для своїх»"] and not any("ЗАЯВКА" in x for x in komu(1))
       and not any("грн" in x or "новий курс" in x for x in komu(777)), str(komu(777)) + str(knopky()))
VYKLYKY.clear(); msg("курс")
ok("вимкнено: слово КУРС на гайд і канал, без цін", knopky() == ["Хочу повний гайд «Світло»", "Канал «для своїх»"]
   and not any("грн" in x for x in komu(777)))
VYKLYKY.clear(); bot.give_guide(777, "t1")
ok("вимкнено: після гайда без пропозиції курсу", not any("два записані курси" in x for x in komu(777)))
ok("вимкнено: після гайда наступний крок канал", any("Гайд ваш" in x for x in komu(777)) and knopky() == ["Канал «для своїх»"], str(knopky()))
VYKLYKY.clear(); cb("t2")
ok("вимкнено: стара кнопка t2 показує чинний гайд, без заявки",
   knopky() == ["Гайд, 900 грн"] and not any("ЗАЯВКА" in x for x in komu(1)) and not any("1200" in x for x in komu(777)), str(komu(777)))
VYKLYKY.clear(); msg("просто питання про щось")
ok("вимкнено: довільний текст дає наступний крок",
   knopky() == ["Забрати три схеми світла", "Хочу повний гайд «Світло»", "Канал «для своїх»"], str(knopky()))
VYKLYKY.clear(); cb("mk:want")
ok("вимкнено: після заявки на МК кнопка каналу", knopky() == ["Канал «для своїх»"])
bot.store.purchases_of = lambda uid: []
VYKLYKY.clear(); msg("/moi", uid=555)
ok("вимкнено: порожні матеріали без курсу, з гайдом", not any("курс" in x.lower() for x in komu(555))
   and "Хочу повний гайд «Світло»" in knopky(555), str(komu(555)))
VYKLYKY.clear(); cb("my:guide", uid=555)
ok("вимкнено: чужий my:guide без курсу", not any("курс" in x.lower() for x in komu(555)))
# Мітла: усі шляхи людини без курсів, «скоро», «записую», «три варіанти», цін t2/t3.
VYKLYKY.clear()
for t in ("/start", "/start guide", "/start fb", "СВІТЛО", "МК", "ЗЙОМКА", "курс", "ретуш", "привіт як справи", "/moi"):
    msg(t, uid=555)
for d in ("magnet", "guide", "t1", "t2", "t3", "retush", "q:new", "q:pro", "k1", "k2", "k12", "mk", "mk:want", "moi", "noget:t1"):
    cb(d, uid=555)
bot.give_magnet(555); bot.give_guide(555, "t1")
_vse = " ".join(komu(555)).lower() + " " + " ".join(
    b["text"].lower() for m, p in VYKLYKY if p.get("chat_id") == 555 and p.get("reply_markup")
    for r in p["reply_markup"]["inline_keyboard"] for b in r)
_zle = [w for w in ("курс", "скоро", "записую", "варіант", "1200", "1900", "розбір кадр", "третю") if w in _vse]
ok("мітла: людина не бачить неіснуючого", not _zle, str(_zle))
ok("вимкнено: /status каже", "продаж курсів ВИМКНЕНО" in bot.status_text())
bot.COURSES_ON = True

# 4. Версії файлів і заливка з роллю
ok("без бази: гайд зі змінної", bot.guide_ref() == "GUIDE")
ok("без бази: версія невідома", "версія невідома" in bot.version_line("guide") and "v13" in bot.version_line("guide"))
ok("магніт не заданий видно", "НЕ ЗАДАНИЙ" in bot.version_line("magnet"))
r = app.post("/zalyvka/sekret?rol=guide", data={"file": (io.BytesIO(b"%PDF"), "Iryna-Rul-SVITLO-guide-2026-09-14-v10.pdf")},
             content_type="multipart/form-data")
ok("стару версію роллю не поставити", r.status_code == 409 and b"NEWFILE" in r.data, r.data.decode()[:120])
r = app.post("/zalyvka/sekret?rol=guide", data={"file": (io.BytesIO(b"%PDF"), "Iryna-Rul-SVITLO-guide-2026-09-23-v13.pdf")},
             content_type="multipart/form-data")
ok("v13 без бази: чесна відмова", r.status_code == 503, r.data.decode()[:120])
r = app.post("/zalyvka/sekret", data={"file": (io.BytesIO(b"%PDF"), "x.pdf")}, content_type="multipart/form-data")
ok("заливка без ролі як раніше", r.status_code == 200 and b"document:NEWFILE" in r.data)

# Роль з базою: підміняємо kv і пошук у пам'яті
KV = {}
bot.store.ON = True
bot.store.kv_get = lambda k, d=None: KV.get(k, d)
bot.store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
bot.store.add_asset = lambda *a, **k: {}
bot.store.asset_by_file_id = lambda f: {"file_name": "Iryna-Rul-SVITLO-guide-2026-09-14-v10.pdf"} if f == "GUIDE" else None
bot.store.session_begin = lambda: None
bot.store.session_end = lambda: None
bot._REF_CACHE.clear()
ok("стара версія з бази видна", bot.version_line("guide").startswith("СТАРА ВЕРСІЯ"), bot.version_line("guide"))
r = app.post("/zalyvka/sekret?rol=magnet", data={"file": (io.BytesIO(b"%PDF"), "Iryna-Rul-3-skhemy-svitla-2026-09-23-v3d.pdf")},
             content_type="multipart/form-data")
ok("магніт v3d роллю ставиться", r.status_code == 200 and KV.get("magnet_file_id") == "NEWFILE", r.data.decode()[:120])
ok("бот віддає новий магніт", bot.magnet_ref() == "NEWFILE" and bot.version_line("magnet").startswith("чинна"), bot.version_line("magnet"))
VYKLYKY.clear(); bot.give_magnet(777)
ok("видача магніта з kv", any(m == "sendDocument" and p.get("document") == "NEWFILE" for m, p in VYKLYKY))
r = app.post("/zalyvka/sekret?rol=guide", data={"file": (io.BytesIO(b"%PDF"), "Iryna-Rul-SVITLO-guide-2026-09-23-v13.pdf")},
             content_type="multipart/form-data")
ok("гайд v13 роллю ставиться", r.status_code == 200 and bot.guide_ref() == "NEWFILE" and "v13" in bot.version_line("guide"))
p = bot.perevirka_lines()
ok("/perevirka каже версії", "версія гайда: чинна" in p and "версія магніта: чинна" in p, p)

print()
if PADINNIA:
    print("ПАДІНЬ:", len(PADINNIA), PADINNIA)
    sys.exit(1)
print("усе зелене")
