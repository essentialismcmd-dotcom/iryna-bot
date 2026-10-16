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

# мітки партнерів retush_<імʼя>
TOUCH, EV = [], []
bot.store.touch_user = lambda u, role="client", source_tag=None: (TOUCH.append(source_tag), {"is_new": True})[1]
bot.store.log_event = lambda uid, kind, data=None: EV.append((kind, data))
for tag, podpys in (("retush_liza", "від Лізи (liza.khbchk)"), ("retush_Anna7", "від anna7")):
    VYKLYKY.clear(); TOUCH.clear(); EV.clear(); KV.clear()
    msg("/start " + tag, uid=880)
    card = sent("sendPhoto", 880) or sent("sendMessage", 880)
    ok(tag + ": людина бачить магніт уроку (як retush)", card and "Чистка шкіри" in (card[0].get("caption") or card[0].get("text") or ""))
    ok(tag + ": source_tag у базі", TOUCH and TOUCH[0] == tag, str(TOUCH))
    ok(tag + ": липка мітка retush", KV.get("tag:880") == "retush", str(KV.get("tag:880")))
    ok(tag + ": подія start з міткою", ("start", {"tag": tag}) in EV, str(EV))
    ok(tag + ": сповіщення з підписом", any(podpys in p.get("text", "") for p in sent(chat=1)), podpys)
VYKLYKY.clear(); TOUCH.clear()
msg("/start retush", uid=881)
ok("звичайний retush без підпису партнера", TOUCH == ["retush"] and not any("(від" in p.get("text", "") for p in sent(chat=1)))
VYKLYKY.clear(); TOUCH.clear()
msg("/start retush_", uid=882)
ok("retush_ без імені не партнер", TOUCH == ["retush_"], str(TOUCH))

# подарунок «Три схеми світла»
os_key = bot.kabinet_mist.KEY
CLAIMED = set()
bot.store.kv_claim = lambda k: (k not in CLAIMED, CLAIMED.add(k))[0]
MAG = {"got": {}}
bot.store.get_user = lambda uid: {"user_id": uid, "got_magnet_at": MAG["got"].get(uid)}
bot.store.mark_magnet = lambda uid: MAG["got"].__setitem__(uid, "now")
bot.store.log_event = lambda uid, kind, data=None: None
bot.magnet_ref = lambda: "MAGNETFILE"
ok("Подарунок: у привітанні магніту ретуші рядок про подарунок",
   bot.RETUSH_MAGNET_HELLO.rstrip().endswith("А після уроку на вас чекає маленький подарунок від мене 🎁"))
def podiia(uid, kind, lesson):
    return app.post("/kabinet-podiia", headers={"X-Kabinet-Key": "k"},
                    json={"user_id": uid, "kind": kind, "lesson": lesson})
bot.store.kv_get = lambda k, d=None: KV.get(k, d)
VYKLYKY.clear()
podiia(900, "start", "1.5")
ok("Подарунок: start подія не шле подарунка", not sent("sendDocument", 900))
podiia(900, "done", "1.4")
ok("Подарунок: done іншого уроку не шле", not sent("sendDocument", 900))
podiia(900, "done", "1.5")
d = sent("sendDocument", 900)
ok("Подарунок: done 1.5 шле PDF магніту з кнопкою каналу",
   d and d[0]["document"] == "MAGNETFILE" and "t.me/test_kanal" in str(d[0].get("reply_markup")), str(d))
ok("Подарунок: текст дослівно", any(p.get("text") == bot.GIFT_DONE for p in sent(chat=900)))
ok("Подарунок: GIFT_DONE дослівно від Yaro",
   bot.GIFT_DONE == "Ви додивились♥️ Як і обіцяла, маленький подарунок: «Три схеми світла з одного сетапу», три різні картинки за одну зйомку без докупки обладнання. Файл нижче" + chr(10) * 2 + "Напишіть, як вам урок? Мені важливо♥️")
VYKLYKY.clear()
KV.pop("kp:900:1.5:done", None)
podiia(900, "done", "1.5")
ok("Подарунок: вдруге не шлеться", not sent("sendDocument", 900))
# людина, що вже взяла магніт
MAG["got"][901] = "x"; VYKLYKY.clear()
podiia(901, "done", "1.5")
ok("Подарунок: тим, хто має магніт, не шлеться", not sent("sendDocument", 901))
# підстраховка 24 год
import datetime as _dt
CAND = [910, 911, 912, 913]
bot.store.gift_candidates = lambda since, h, skip, skip_kv=None: [c for c in CAND if c not in skip]
KV["kp:911:1.5:done"] = "1"
bot.owned_keys = (lambda orig: (lambda uid, real=False: {"t1"} if uid == 912 and real else orig(uid, real)))(bot.owned_keys)
night = _dt.datetime(2026, 10, 12, 21, 30, tzinfo=_dt.timezone.utc)      # 00:30 Київ
day = _dt.datetime(2026, 10, 12, 9, 0, tzinfo=_dt.timezone.utc)          # 12:00 Київ
VYKLYKY.clear()
ok("Підстраховка: вночі не шле", bot.gift_late_run(night) == 0 and not sent("sendDocument"))
n = bot.gift_late_run(day)
docs = [p["chat_id"] for p in sent("sendDocument") if p.get("document") == "MAGNETFILE"]
ok("Підстраховка: вдень шле лише без done і без покупок (910, 913; 911 done, 912 купила)", n == 2 and docs == [910, 913], str(docs))
ok("Підстраховка: текст", any(p.get("text") == bot.GIFT_LATE for p in sent(chat=910)))
VYKLYKY.clear()
ok("Підстраховка: вдруге не шле", bot.gift_late_run(day) == 0 and not sent("sendDocument"))

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
