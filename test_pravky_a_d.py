#!/usr/bin/env python3
"""
Правки А-Д 12.10 БЕЗ мережі і бази: відсів дублів у polling, заявки раз на добу,
постійна кнопка «Мої матеріали», покупцю матеріали замість оплати/інстаграма,
урок кнопкою в кабінет. Запуск: python test_pravky_a_d.py
"""
import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "GUIDE_FILE_ID": "GUIDE", "NOTIFY_IDS": "1",
                   "CHANNEL_URL": "https://t.me/test_kanal", "COURSES_ON": "1",
                   "PAY_URL": "https://pay.test/jar", "COURSE_BUNDLE_ONLY": "1",
                   "COURSE1_FILES": "Урок 1 · основи > video:V1, document:D1 | Урок 2 · бʼюті > video:V2, document:D2",
                   "COURSE2_FILES": "", "KABINET_URL": "https://kab.test", "KABINET_KEY": "k"})
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
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import bot

bot.time.sleep = lambda s: None
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
    return app.post("/sekret", json={"callback_query": {"id": "c", "data": data, "from": {"id": uid},
                    "message": {"chat": {"id": uid}, "message_id": 5}}})


def sent(method="sendMessage", chat=None):
    return [p for m, p in VYKLYKY if m == method and (chat is None or p.get("chat_id") == chat)]


# А: ключі дублів
k1 = bot._dedup_key({"callback_query": {"id": "1", "data": "magnet", "from": {"id": 5}}})
ok("А ключ кнопки", k1 == (5, "cb:magnet"), str(k1))
ok("А ключ /start", bot._dedup_key({"message": {"from": {"id": 5}, "text": "/start retush"}}) == (5, "msg:/start retush"))
ok("А ключ «Мої матеріали»", bot._dedup_key({"message": {"from": {"id": 5}, "text": "Мої матеріали"}}) == (5, "msg:мої матеріали"))
ok("А довільний текст без ключа", bot._dedup_key({"message": {"from": {"id": 5}, "text": "привіт, як справи"}}) is None)
bot._recent[(5, "cb:x")] = float("inf")
ok("А дубль, поки йде", bot._is_dup((5, "cb:x"), 100.0))
bot._recent[(5, "cb:x")] = 100.0
ok("А дубль через 5 с", bot._is_dup((5, "cb:x"), 105.0))
ok("А не дубль через 15 с", not bot._is_dup((5, "cb:x"), 115.0))
ok("А блокування лише для видач", bot._user_lock(5, "les:k1:0") is not None and bot._user_lock(5, "mk:want") is None)

# В: заявки раз на добу (kv у пам'яті)
KV = {}
bot.store.kv_get = lambda k, d=None: KV.get(k, d)
bot.store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
VYKLYKY.clear()
cb("mk:want", 777); cb("mk:want", 777)
ok("В МК: людині відповіли двічі", len(sent(chat=777)) == 2)
ok("В МК: персоналу одна заявка", len([p for p in sent(chat=1) if "ЗАЯВКА НА МК" in p["text"]]) == 1)
VYKLYKY.clear()
cb("k12z", 778); cb("k12z", 778)
ok("В курс: персоналу одна заявка", len([p for p in sent(chat=1) if "ЗАЯВКА" in p["text"]]) == 1)
ok("В інша людина має власну заявку", (cb("k12z", 779), len([p for p in sent(chat=1) if "ЗАЯВКА" in p["text"]]))[1] == 2)

# Б: постійна клавіатура
VYKLYKY.clear()
msg("/moi", 780)
p = sent(chat=780)[-1]
ok("Б /moi без покупок: інлайн-кнопки", "inline_keyboard" in (p.get("reply_markup") or {}))
bot.api("sendMessage", chat_id=999, text="x")
ok("Б чужому chat_id клавіатури нема", "reply_markup" not in sent(chat=999)[-1])
bot._tm.person = 780
bot.api("sendMessage", chat_id=780, text="x")
ok("Б повідомлення без кнопок має постійну клавіатуру",
   (sent(chat=780)[-1].get("reply_markup") or {}).get("is_persistent") is True)
bot._tm.person = None
ok("Б курс у порожніх «Мої матеріали»", any(b["callback_data"] == "retush"
   for r in bot.empty_kb(780)["inline_keyboard"] for b in r if "callback_data" in b))

# Б: покупець
BUY = {"purchases": [{"tier": "k12z", "status": "paid"}]}
bot.store.purchases_of = lambda uid, only_paid=True: BUY["purchases"] if uid == 790 else []
VYKLYKY.clear()
msg("привіт, а де мої відео", 790)
p = sent(chat=790)[-1]
rows = (p.get("reply_markup") or {}).get("inline_keyboard", [])
ok("Б довільний текст покупця веде до уроків", any(str(b.get("callback_data", "")).startswith("les:") for r in rows for b in r), p["text"][:40])
VYKLYKY.clear()
msg("/kurs", 790)
p = sent(chat=790)[-1]
ok("Б /kurs покупцю: матеріали, не оплата", p["text"] == bot.COURSE_OWNED and not any("pay.test" in str(b) for b in p["reply_markup"]["inline_keyboard"]))
VYKLYKY.clear()
cb("retush", 790)
ok("Б кнопка «Курс ретуші» покупцю", sent(chat=790)[-1]["text"] == bot.COURSE_OWNED)
VYKLYKY.clear()
msg("/kurs", 791)
ok("Б /kurs не покупцю: картка з оплатою", "Оплат" in str(sent(chat=791)[-1]["reply_markup"]))

# Г: урок кнопкою в кабінет
VYKLYKY.clear()
cb("les:k1:1", 790)
msgs = sent(chat=790)
web = [b for p in msgs for r in (p.get("reply_markup") or {}).get("inline_keyboard", []) for b in r if "web_app" in b]
ok("Г кнопка web_app у кабінет на уроці 2", web and web[0]["web_app"]["url"] == "https://kab.test/?p=2.1", str(web))
ok("Г відео не шлеться в чат", not sent("sendVideo", 790))
ok("Г практика шлеться", len(sent("sendDocument", 790)) == 1)
ok("Г текст завершення без «дивитись тут»", "Відео дивіться в моєму кабінеті" in msgs[-1]["text"])

# /vydaty gaid
VYKLYKY.clear()
msg("/vydaty 9201 gaid", uid=1)
ok("/vydaty gaid: людині документ-гайд", any(m == "sendDocument" and p.get("chat_id") == 9201 and p.get("document") == "GUIDE" for m, p in VYKLYKY))
ok("/vydaty gaid: адмін отримав Видано", any("Видано" in p.get("text", "") for p in sent(chat=1)))
VYKLYKY.clear()
msg("/vydaty 9202", uid=1)
ok("/vydaty без аргументу: курс, не гайд", not any(m == "sendDocument" and p.get("document") == "GUIDE" for m, p in VYKLYKY))

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
