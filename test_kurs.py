#!/usr/bin/env python3
"""
Перевірка лійки курсу ретуші БЕЗ мережі, бази і телеграма.

Запуск:  python test_kurs.py
Виходить 0, якщо все зелене. BOT_TOKEN підставний, NO_THREADS=1 глушить
потоки, requests.post підмінений: усі виклики Telegram лягають у список.
"""

import os, sys, json

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ["BOT_TOKEN"] = "test:token"
os.environ["WEBHOOK_SECRET"] = "sekret"
os.environ["ADMIN_ID"] = "1"
os.environ["NO_THREADS"] = "1"
os.environ["TEST_MODE"] = "1"
os.environ["PAY_URL"] = "https://send.monobank.ua/jar/test"
os.environ["GUIDE_FILE_ID"] = "GUIDE"
os.environ["COURSE1_FILES"] = "video:V1, document:D1,BARE"
os.environ["COURSE2_FILES"] = "video:V2"
os.environ["COURSE_PRICES"] = "1400,1300,2700"
os.environ.pop("DATABASE_URL", None)

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
        return _R({"ok": True, "result": {"document": {"file_id": "NEWGUIDE"}}})
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post

import bot

USER = {"id": 777, "first_name": "Тест", "username": "test"}
app = bot.app.test_client()
PADINNIA = []


def msg(text, uid=777, **extra):
    m = {"message_id": 1, "chat": {"id": uid}, "from": dict(USER, id=uid), "text": text}
    m.update(extra)
    return app.post("/sekret", json={"message": m})


def cb(data, uid=777):
    return app.post("/sekret", json={"callback_query": {
        "id": "cq", "data": data, "from": dict(USER, id=uid),
        "message": {"chat": {"id": uid}, "message_id": 5}}})


def perevirka(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


def teksty(method="sendMessage"):
    return [v[1].get("text", "") for v in VYKLYKY if v[0] == method]


def ostannia_klaviatura(chat_id=777):
    """Остання клавіатура, надіслана саме людині, не адміну."""
    for m, p in reversed(VYKLYKY):
        if m == "sendMessage" and p.get("reply_markup") and p.get("chat_id") == chat_id:
            return [b["text"] for row in p["reply_markup"]["inline_keyboard"] for b in row]
    return []


# 1. Ціни зі змінної
perevirka("ціни зі змінної", (bot._K1, bot._K2, bot._K12) == (1400, 1300, 2700))
perevirka("коди продуктів", [bot.PRODUCTS[k]["code"] for k in ("t1", "t2", "t3", "k1", "k2", "k12")]
          == ["1", "2", "3", "4", "5", "6"])
perevirka("файли курсів", bot.COURSE_FILES["k1"] == [("video", "V1"), ("document", "D1"), ("document", "BARE")]
          and bot.COURSE_FILES["k12"] == bot.COURSE_FILES["k1"] + [("video", "V2")])

# 2. /start і магніт
VYKLYKY.clear()
msg("/start")
perevirka("старт вітає", any("Привіт" in x for x in teksty()))

# 3. Курс: кнопка після магніта
VYKLYKY.clear()
bot.MAGNET_URL = "https://x/magnit.pdf"
cb("magnet")
perevirka("після магніта є кнопка курсу", "Курс ретуші" in ostannia_klaviatura(), str(ostannia_klaviatura()))

# 4. Кваліфікатор
VYKLYKY.clear()
cb("retush")
perevirka("кваліфікатор", "фотошопом" in teksty()[-1] and ostannia_klaviatura() == ["Тільки починаю", "Вже працюю у фотошопі"])

VYKLYKY.clear()
cb("q:new")
perevirka("новачку перший курс", ostannia_klaviatura() == ["Перший курс, 1400 грн", "Обидва курси, 2700 грн"], str(ostannia_klaviatura()))
VYKLYKY.clear()
cb("q:pro")
perevirka("досвідченому другий", ostannia_klaviatura() == ["Другий курс, 1300 грн", "Обидва курси, 2700 грн"], str(ostannia_klaviatura()))

# 5. Вибір курсу: код платежу і заявка адміну
VYKLYKY.clear()
cb("k12")
kod = bot.order_code(777, "k12")
perevirka("код платежу курсу", kod == "IR" + bot.b36(777) + "-6", kod)
t = teksty()
perevirka("клієнту текст із кодом", any(kod in x and "2700 грн" in x for x in t))
perevirka("адміну заявка з кнопкою", any("ЗАЯВКА" in x and "Обидва курси" in x for x in t))
perevirka("кнопка «оплатив, а файлу немає»", "Оплатив, а файлу немає" in ostannia_klaviatura())

# 6. Старий гайд працює як і раніше
VYKLYKY.clear()
cb("t1")
perevirka("код гайда старого виду", bot.order_code(777, "t1") == "IR" + bot.b36(777) + "-1")

# 7. Тестова оплата курсу: файли летять правильними методами
VYKLYKY.clear()
cb("paid:k12")
metody = [m for m, _ in VYKLYKY if m.startswith("send") and m != "sendMessage"]
perevirka("видача обох курсів", metody == ["sendVideo", "sendDocument", "sendDocument", "sendVideo"], str(metody))
perevirka("відео летить як video", any(m == "sendVideo" and p.get("video") == "V1" for m, p in VYKLYKY))
perevirka("текст після видачі", any("доступ залишається назавжди" in x for x in teksty()))

# 8. Тестова оплата гайда: після гайда пропозиція курсу
VYKLYKY.clear()
cb("paid:t1")
perevirka("гайд пішов", any(m == "sendDocument" and p.get("document") == "GUIDE" for m, p in VYKLYKY))
perevirka("після гайда кнопка курсу", "Курс ретуші" in ostannia_klaviatura())

# 9. Оплата з банки за кодом курсу
VYKLYKY.clear()
bot.handle_tx({"id": "tx1", "amount": 130000, "comment": kod.replace("-6", "-5"), "time": 0})
perevirka("банка: другий курс видано", any(m == "sendVideo" and p.get("video") == "V2" for m, p in VYKLYKY)
          and any("видано автоматично" in x for x in teksty()))
VYKLYKY.clear()
bot.handle_tx({"id": "tx2", "amount": 100000, "comment": kod, "time": 0})
perevirka("банка: недоплата за обидва не видає", not [m for m, _ in VYKLYKY if m == "sendVideo"]
          and any("а треба 2700" in x for x in teksty()))
VYKLYKY.clear()
bot.handle_tx({"id": "tx3", "amount": 65000, "comment": "IR" + bot.b36(777) + "-1", "time": 0})
perevirka("банка: гайд за старим кодом", any(p.get("document") == "GUIDE" for m, p in VYKLYKY))

# 10. Курс без файлів: не видається, адмін бачить причину
VYKLYKY.clear()
bot.COURSE_FILES["k2"] = []
cb("paid:k2")
perevirka("порожній курс не видається", any("не задані" in x for x in teksty()))
bot.COURSE_FILES["k2"] = [("video", "V2")]

# 11. Ручна видача адміном
VYKLYKY.clear()
cb("give:777:k1", uid=1)
perevirka("ручна видача курсу", any(m == "sendVideo" for m, _ in VYKLYKY) and "Видано" in teksty())

# 12. Адмін кидає відео: отримує рядок kind:file_id
VYKLYKY.clear()
msg("", uid=1, video={"file_id": "VID123", "file_size": 52428800})
perevirka("адміну file_id відео", any("video:VID123" in x and "50.0 МБ" in x for x in teksty()), str(teksty()))
VYKLYKY.clear()
msg("", uid=1, document={"file_id": "DOC1"})
perevirka("адміну file_id документа", any("document:DOC1" in x for x in teksty()))

# 13. /status і /inbox не падають без бази
VYKLYKY.clear()
msg("/status", uid=1)
perevirka("/status показує курси", any("Курс 1: у курсі 3 файлів" in x and "1400 / 1300 / 2700" in x for x in teksty()), str(teksty()))
VYKLYKY.clear()
msg("/inbox", uid=1)
perevirka("/inbox без бази", any("немає" in x for x in teksty()))

# 14. Заливка гайда
VYKLYKY.clear()
bot.GUIDE_UPLOAD_PATH = "files/Iryna-Rul-SVITLO-guide-2026-08-31-v9.pdf"
bot.time.sleep = lambda s: None
bot.upload_guide()
perevirka("заливка гайда дає file_id адміну", any("NEWGUIDE" in x for x in teksty()), str(teksty()))

# 15. /privacy живий
perevirka("/privacy віддає сторінку", app.get("/privacy").status_code == 200)

print()
if PADINNIA:
    print("ПАДІНЬ:", len(PADINNIA), PADINNIA)
    sys.exit(1)
print("усе зелене")
