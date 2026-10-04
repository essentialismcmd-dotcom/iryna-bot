#!/usr/bin/env python3
"""
Мітка ?start=mk (закріп каналу «Хочу на майстер-клас») БЕЗ мережі, бази і
телеграма: людина одразу бачить опис МК з кнопкою заявки, той самий екран, що
на слово «МК» і кнопку mk; мітка mk окремим рядком у /stats. Запуск: python test_myitka_mk.py
"""
import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "MAGNET_URL": "MAGNIT",
                   "NOTIFY_IDS": "1", "CHANNEL_URL": "https://t.me/test_kanal",
                   "START_PIC": "PIC_START", "CARD_MAGNIT": "PIC_MAGNIT", "CARD_GUIDE": "PIC_GUIDE",
                   "CARD_KANAL": "PIC_KANAL", "CARD_MK": "PIC_MK", "CHANNEL_LOCK": "0",
                   "PAY_URL": "https://pay.test/jar"})
for k in ("DATABASE_URL", "COURSES_ON", "GUIDE_PRICE", "COURSE_PRICES"):
    os.environ.pop(k, None)

import requests
VYKLYKY = []
ZLAMANE_FOTO = set()


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None):
    method = url.rsplit("/", 1)[-1]
    p = json or data or {}
    VYKLYKY.append((method, p))
    if method == "sendPhoto" and p.get("photo") in ZLAMANE_FOTO:
        return _R({"ok": False, "error_code": 400, "description": "wrong file identifier"})
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
    VYKLYKY.clear()
    app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": uid},
             "from": {"id": uid, "first_name": "Т"}, "text": text}})


def cb(data, uid=777):
    VYKLYKY.clear()
    app.post("/sekret", json={"callback_query": {"id": "c", "data": data,
             "from": {"id": uid, "first_name": "Т"}, "message": {"chat": {"id": uid}, "message_id": 5}}})


def pobachene(uid=777):
    return [(m, p.get("photo"), p.get("caption") or p.get("text"), p.get("reply_markup"))
            for m, p in VYKLYKY if m in ("sendPhoto", "sendMessage") and p.get("chat_id") == uid]


PODII = []
bot.store.log_event = lambda uid, kind, payload=None: PODII.append((uid, kind, payload))

# 1. ?start=mk: картка МК з кнопкою заявки, без вітання з магнітом
msg("/start mk")
z_mitky = pobachene()
ok("/start mk: одне повідомлення", len(z_mitky) == 1, str(z_mitky))
ok("/start mk: фото CARD_MK з MK_TEXT", z_mitky and z_mitky[0][:3] == ("sendPhoto", "PIC_MK", bot.MK_TEXT), str(z_mitky)[:200])
ok("/start mk: кнопка «Хочу на майстер-клас»", z_mitky and z_mitky[0][3] == bot.mk_kb()
   and bot.mk_kb()["inline_keyboard"][0][0] == {"text": "Хочу на майстер-клас", "callback_data": "mk:want"})
ok("/start mk: магніту і HELLO нема", not any(x[2] == bot.HELLO for x in z_mitky))
ok("/start mk: подія start з міткою mk", (777, "start", {"tag": "mk"}) in PODII, str(PODII))
ok("/start mk: подія mk_entry", any(k == "mk_entry" for _, k, _ in PODII), str(PODII))

# 2. той самий екран, що слово «МК» і кнопка mk
msg("МК")
ok("слово МК: те саме, що ?start=mk", pobachene() == z_mitky, str(pobachene())[:200])
cb("mk")
ok("кнопка mk: те саме, що ?start=mk", pobachene() == z_mitky, str(pobachene())[:200])

# 3. кнопка заявки після мітки працює як завжди
PODII.clear()
cb("mk:want")
ok("заявка: подія mk_want", any(k == "mk_want" for _, k, _ in PODII), str(PODII))
ok("заявка: людина бачить MK_THANKS", any(x[2] == bot.MK_THANKS for x in pobachene()), str(pobachene())[:200])

# 4. фото не прийнялось: той самий текст з кнопкою
ZLAMANE_FOTO.add("PIC_MK")
msg("/start mk")
ok("фото зламане: MK_TEXT текстом з кнопкою", pobachene()[-1:] == [("sendMessage", None, bot.MK_TEXT, bot.mk_kb())],
   str(pobachene())[:200])
ZLAMANE_FOTO.clear()

# 5. інші мітки не зачеплені
msg("/start kanal")
ok("/start kanal: як раніше HELLO з магнітом", pobachene() and pobachene()[0][2] == bot.HELLO
   and pobachene()[0][3] == bot.magnet_kb())

# 6. /stats: мітка mk окремим рядком
bot.store.ON = True
bot.store.starts_stats = lambda skip: {"people": 5, "presses": 7, "day": 2, "week": 5, "magnet": 1,
    "tags": [{"tag": "inst", "people": 3, "presses": 4}, {"tag": "mk", "people": 2, "presses": 3}]}
tx = bot.starts_text()
ok("/stats: mk окремим рядком", "  mk: 2 / 3" in tx and "  inst: 3 / 4" in tx, tx)
bot.store.ON = False

# 7. закріп за замовчуванням веде на ?start=mk
ok("закріп: кнопка «Хочу на майстер-клас» → ?start=mk",
   bot.ZAKRIP_BTN == "Хочу на майстер-клас" and bot.ZAKRIP_URL == "https://t.me/iryna_rul_bot?start=mk")

print("\nПАДІНЬ:", len(PADINNIA))
sys.exit(1 if PADINNIA else 0)
