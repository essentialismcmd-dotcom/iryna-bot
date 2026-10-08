#!/usr/bin/env python3
"""Живий фідбек (БЕЗ мережі і бази): фото покупця -> forwardMessage адміну й Ірі;
reply адміна/Іри -> copyMessage людині. Запуск: python test_fidbek.py"""
import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "MAGNET_URL": "MAGNIT",
                   "NOTIFY_IDS": "1", "IRA_ID": "2", "IRA_ON": "1", "START_PIC": "PIC_START",
                   "CHANNEL_LOCK": "0", "COURSES_ON": "1", "COURSE_BUNDLE_ONLY": "1",
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
    return _R({"ok": True, "result": {"message_id": 1000 + len(VYKLYKY)}})


requests.post = fake_post
import bot

app = bot.app.test_client()
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


def post(m):
    VYKLYKY.clear()
    app.post("/sekret", json={"message": m})
    return list(VYKLYKY)


KLIENT = 777000
foto = post({"message_id": 50, "chat": {"id": KLIENT}, "from": {"id": KLIENT, "first_name": "Оля"},
             "photo": [{"file_id": "S", "file_unique_id": "s"}, {"file_id": "B", "file_unique_id": "b"}],
             "caption": "моя ретуш"})
fw = [p["chat_id"] for m, p in foto if m == "forwardMessage" and p.get("from_chat_id") == KLIENT]
ok("фото переслано адміну й Ірі", sorted(fw) == [1, 2], str(fw))
hd = [p for m, p in foto if m == "sendMessage" and p["chat_id"] == 2]
ok("підпис: хто і чи купила", bool(hd) and "Оля" in hd[0]["text"] and "id 777000" in hd[0]["text"]
   and "курс не купувала" in hd[0]["text"])

# reply адміна на переслане фото (id пересланого = 1000+номер виклику)
fwd_ids = {}
for i, (m, p) in enumerate(foto):
    if m == "forwardMessage":
        fwd_ids[p["chat_id"]] = 1000 + i + 1
for staff, nazva in ((1, "адміна"), (2, "Іри")):
    r = post({"message_id": 60, "chat": {"id": staff}, "from": {"id": staff, "first_name": "S"},
              "text": "Гарно, підніми тіні",
              "reply_to_message": {"message_id": fwd_ids[staff], "chat": {"id": staff}}})
    cp = [p for m, p in r if m == "copyMessage"]
    ok("reply " + nazva + " -> copyMessage людині",
       len(cp) == 1 and cp[0]["chat_id"] == KLIENT and cp[0]["from_chat_id"] == staff and cp[0]["message_id"] == 60)

# reply на текстове сповіщення без пам'яті: id з тексту
r = post({"message_id": 61, "chat": {"id": 1}, "from": {"id": 1}, "text": "ок",
          "reply_to_message": {"message_id": 5, "text": "Повідомлення в боті від Оля, без юзернейма, id 777000:\nпривіт"}})
ok("reply на сповіщення з id", [p["chat_id"] for m, p in r if m == "copyMessage"] == [KLIENT])

# reply Іри не йде в матеріали
r = post({"message_id": 62, "chat": {"id": 2}, "from": {"id": 2}, "text": "ок",
          "reply_to_message": {"message_id": fwd_ids[2], "chat": {"id": 2}}})
ok("reply Іри не в матеріали", not any(m == "forwardMessage" for m, p in r))
# звичайний матеріал Іри (не reply) далі йде в матеріали
r = post({"message_id": 63, "chat": {"id": 2}, "from": {"id": 2}, "text": "матеріал"})
ok("не-reply Іри не копіюється людині", not any(m == "copyMessage" for m, p in r))

# текст людини іде і Ірі
r = post({"message_id": 70, "chat": {"id": KLIENT}, "from": {"id": KLIENT, "first_name": "Оля"}, "text": "питання по ретуші"})
ok("текст людини: сповіщення адміну й Ірі",
   sorted(p["chat_id"] for m, p in r if m == "sendMessage" and "питання по ретуші" in p.get("text", "") and p["chat_id"] in (1, 2)) == [1, 2])

print("\nПАДІННЯ: " + str(PADINNIA) if PADINNIA else "\nУсе зелене")
sys.exit(1 if PADINNIA else 0)
