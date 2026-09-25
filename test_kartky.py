#!/usr/bin/env python3
"""
Картки брендингу (25.09) БЕЗ мережі, бази і телеграма: з картинкою в змінній
повідомлення лійки йдуть фото з підписом і тими самими кнопками; фото не
прийнялось або текст довший за 1024: звичайний текст. Запуск: python test_kartky.py
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
                   "CARD_KANAL": "PIC_KANAL", "CARD_MK": "PIC_MK", "CHANNEL_LOCK": "0"})
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


def foto(uid=777):
    return [p for m, p in VYKLYKY if m == "sendPhoto" and p.get("chat_id") == uid]


def teksty(uid=777):
    return [p for m, p in VYKLYKY if m == "sendMessage" and p.get("chat_id") == uid]


msg("/start")
f = foto()
ok("/start: фото START_PIC", len(f) == 1 and f[0]["photo"] == "PIC_START")
ok("/start: підпис це HELLO дослівно", f and f[0]["caption"] == bot.HELLO)
ok("/start: кнопка магніта на фото", f and f[0]["reply_markup"] == bot.magnet_kb())
ok("/start: окремого тексту нема", not teksty())

msg("/start guide")
f = foto()
ok("/start guide: фото START_PIC з текстом гайда", f and f[0]["photo"] == "PIC_START"
   and f[0]["caption"] == bot.GUIDE_HELLO_NOC)

cb("magnet")
f = foto()
ok("магніт: спершу файл, потім картка", [m for m, _ in VYKLYKY if m in ("sendDocument", "sendPhoto")]
   == ["sendDocument", "sendPhoto"])
ok("магніт: CARD_MAGNIT з AFTER_NOC", f and f[0]["photo"] == "PIC_MAGNIT" and f[0]["caption"] == bot.AFTER_NOC)

cb("guide")
f = foto()
ok("гайд: CARD_GUIDE з тарифом", f and f[0]["photo"] == "PIC_GUIDE" and "Повний гайд" in f[0]["caption"]
   and f[0]["reply_markup"] == bot.tiers_kb())

msg("світло")
ok("слово СВІТЛО: CARD_GUIDE", foto() and foto()[0]["photo"] == "PIC_GUIDE")

cb("mk")
ok("МК: CARD_MK з MK_TEXT", foto() and foto()[0]["photo"] == "PIC_MK" and foto()[0]["caption"] == bot.MK_TEXT)
msg("мк")
ok("слово МК: CARD_MK", foto() and foto()[0]["photo"] == "PIC_MK")

ok("гайд видано: CARD_KANAL після файла", bot.give_guide(777, "t1") and foto()
   and foto()[-1]["photo"] == "PIC_KANAL" and foto()[-1]["caption"] == bot.NEXT_AFTER_GUIDE_NOC)

# Фолбеки
ZLAMANE_FOTO.add("PIC_MK")
cb("mk")
ok("фото не прийнялось: той самий текст звичайним повідомленням",
   teksty() and teksty()[0]["text"] == bot.MK_TEXT and teksty()[0]["reply_markup"] == bot.mk_kb())
ZLAMANE_FOTO.clear()

VYKLYKY.clear()
bot.send_card(777, "PIC_START", "я" * 1025, None)
ok("підпис довший за 1024: лише текст", not foto() and len(teksty()) == 1)

VYKLYKY.clear()
bot.send_card(777, "", "текст", None)
ok("порожня змінна: лише текст", not foto() and teksty() and teksty()[0]["text"] == "текст")

for nazva in ("HELLO", "GUIDE_HELLO_NOC", "AFTER_NOC", "LOCK_TEXT", "MK_TEXT", "NEXT_AFTER_GUIDE_NOC"):
    ok("довжина %s ≤ 1024" % nazva, len(getattr(bot, nazva)) <= 1024, str(len(getattr(bot, nazva))))
ok("довжина вступу гайда ≤ 1024", len(bot.guide_intro(bot.tiers_kb())) <= 1024)

print("\nПАДІНЬ:", len(PADINNIA))
sys.exit(1 if PADINNIA else 0)
