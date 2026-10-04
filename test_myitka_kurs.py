#!/usr/bin/env python3
"""Мітка /start kurs і команда /kurs (БЕЗ мережі і бази): одразу пропозиція курсу 3 300;
з вимкненими курсами /start kurs показує звичайний старт. Запуск: python test_myitka_kurs.py"""
import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "MAGNET_URL": "MAGNIT",
                   "NOTIFY_IDS": "1", "START_PIC": "PIC_START", "CHANNEL_LOCK": "0",
                   "COURSES_ON": "1", "COURSE_BUNDLE_ONLY": "1",
                   "COURSE_PRICES": "3200,1900,3300", "PAY_URL": "https://pay.test/jar"})
os.environ.pop("DATABASE_URL", None)

import requests
VYKLYKY = []


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None):
    VYKLYKY.append((url.rsplit("/", 1)[-1], json or data or {}))
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
    return [p for m, p in VYKLYKY if m in ("sendMessage", "sendPhoto") and p.get("chat_id") == uid]


def btns(p):
    return [b for row in (p.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]


for cmd in ("/start kurs", "/kurs"):
    out = msg(cmd)
    t = (out[0].get("text") or out[0].get("caption") or "") if out else ""
    ok(cmd + ": одне повідомлення з карткою курсу", len(out) == 1 and "Курс ретуші, 3300 грн" in t, t[:60])
    ok(cmd + ": що всередині", all(x in t for x in ("18 відео", "135 хвилин", "4 уроки",
       "бʼюті-портрет", "темний фон", "фешн-колір", "пресети", "Доступ назавжди",
       "щодоби після оплати")))
    ok(cmd + ": код платежу -6", "-6" in t, t[-60:].replace(chr(10), " "))
    ok(cmd + ": без Stars", "Stars" not in t and "star" not in t.lower())
    ok(cmd + ": кнопка оплати карткою", any("pay.test" in (b.get("url") or "") for b in btns(out[0])))

ok("меню: є /kurs «Курс ретуші»", {"command": "kurs", "description": "Курс ретуші"} in bot.PEOPLE_COMMANDS)

# курси вимкнені: /start kurs не ламається, звичайний старт
bot.COURSES_ON = False
out = msg("/start kurs")
ok("COURSES_ON=0: /start kurs показує звичайний старт (картка START_PIC)",
   len(out) == 1 and out[0].get("photo") == "PIC_START", str(out)[:120])
ok("COURSES_ON=0: без пропозиції курсу",
   "3300" not in str(out) and not any(b.get("callback_data") == "k12" for b in btns(out[0])))
out = msg("/kurs")
ok("COURSES_ON=0: /kurs не ламається", len(out) == 1, str(out)[:80])
bot.COURSES_ON = True

print("\nПАДІНЬ:", len(PADINNIA))
sys.exit(1 if PADINNIA else 0)
