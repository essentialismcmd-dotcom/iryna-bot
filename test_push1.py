#!/usr/bin/env python3
"""
Розсилка push1 (13.10) БЕЗ мережі і бази: сегменти A (магніт чи урок 1.5, без покупок), B (курс),
G (гайд без курсу); виключення (персонал, PUSH_SKIP_IDS, push1 уже був, 403, «стоп», бот писав за 24 год);
/push1 перегляд лише тому, хто питає; /push1 go раз на людину, ~1 на секунду, лише 10:00–20:00 за Києвом,
403 = позначка blocked, звіт тому, хто запустив; сторінка /push1/<S>; тексти з push1.txt і змінних.
Нікому з людей тут нічого не йде: requests.post підставний. Запуск: python -B test_push1.py
"""
import os, sys
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

INVITE = "https://t.me/+TESTinvite"
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "IRA_ID": "2",
                   "NO_THREADS": "1", "NOTIFY_IDS": "1,2", "CHANNEL_URL": "https://t.me/test_kanal",
                   "PUSH_SKIP_IDS": "901, 902", "PUSH1_URL": INVITE})
for _k in ("DATABASE_URL", "PUSH1_A", "PUSH1_B", "PUSH1_G", "PUSH1_KNOPKA", "LEAD_IDS"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []
ZBII = {105, 140, -100500}                     # 403: заблокували бота
POMYLKA = {107}                                # 400: інша причина
RATE = {102: 1}                                # скільки разів дати 429


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    method = url.rsplit("/", 1)[-1]
    p = json or data or {}
    VYKLYKY.append((method, p))
    cid = p.get("chat_id")
    if cid in ZBII:
        return _R({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
    if cid in POMYLKA:
        return _R({"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})
    if RATE.get(cid):
        RATE[cid] -= 1
        return _R({"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 2",
                   "parameters": {"retry_after": 2}})
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import bot

SNY = []
bot.time.sleep = lambda s: SNY.append(s)
bot.kabinet_mist.push_user = lambda uid: None
bot.push1_spawn = lambda fn: fn()               # розсилка синхронно: перевірка без гонок
HOUR = [12]
bot.kyiv_hour = lambda now=None: HOUR.pop(0) if len(HOUR) > 1 else HOUR[0]
app = bot.app.test_client()
PADINNIA = []


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


# ---------- підставна база в памʼяті (та сама поведінка, що store.py і PUSH_SQL) ----------
NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=3)
FRESH = NOW - timedelta(hours=2)
DB = {"kv": {}, "kv_at": {}, "users": {}, "purchases": {}, "events": []}


def kv_set(k, v):
    DB["kv"][k] = str(v)
    DB["kv_at"][k] = datetime.now(timezone.utc)


def kv_claim(k):
    if k in DB["kv"]:
        return False
    kv_set(k, "1")
    return True


def log_event(uid, kind, payload=None, at=None):
    DB["events"].append((uid, kind, payload, at or datetime.now(timezone.utc)))


def touch_user(u, role="client", source_tag=None):
    uid = u.get("id")
    new = uid not in DB["users"]
    old = DB["users"].get(uid, {})
    DB["users"][uid] = dict(old, user_id=uid, username=u.get("username"), first_name=u.get("first_name"),
                            last_name=u.get("last_name"), role=role, last_seen_at=datetime.now(timezone.utc),
                            source_tag=old.get("source_tag") or source_tag or None)
    return dict(DB["users"][uid], is_new=new)


def push_rows():
    if not S.ON:
        return None
    paid = [p for p in DB["purchases"].values() if p["status"] in ("paid", "delivered")]
    ids = set(DB["users"]) | {p["user_id"] for p in paid} | {e[0] for e in DB["events"] if e[0] is not None}
    rows = []
    for uid in sorted(ids):
        u = DB["users"].get(uid, {})
        evs = [e for e in DB["events"] if e[0] == uid]
        texts = [e[2].get("text") for e in evs if e[1] == "message" and e[2] and e[2].get("text")]
        rows.append({
            "user_id": uid, "username": u.get("username"), "first_name": u.get("first_name"),
            "last_name": u.get("last_name"), "role": u.get("role"), "source_tag": u.get("source_tag"),
            "got_magnet_at": u.get("got_magnet_at"), "last_seen_at": u.get("last_seen_at"),
            "ev_magnet": any(e[1] == "magnet" for e in evs), "ev_lesson": any(e[1] == "retush_entry" for e in evs),
            "kab_lesson": any(k.startswith("kp:%s:1.5:" % uid) for k in DB["kv"]),
            "tiers": sorted({p["tier"] for p in paid if p["user_id"] == uid and p["tier"]}),
            "last_event": max((e[3] for e in evs), default=None),
            "texts": "\n".join(texts) or None,
            "blocked_at": DB["kv_at"].get("blocked:%s" % uid),
            "push1": DB["kv"].get("push1:%s" % uid)})
    return rows


S = bot.store
S.ON = True
S.kv_get = lambda k, d=None: DB["kv"].get(k, d)
S.kv_set = kv_set
S.kv_claim = kv_claim
S.touch_user = touch_user
S.get_user = lambda uid: DB["users"].get(uid)
S.log_event = lambda uid, kind, payload=None: log_event(uid, kind, payload)
S.purchases_of = lambda uid, only_paid=True: [dict(p) for p in DB["purchases"].values() if p["user_id"] == uid
                                              and (not only_paid or p["status"] in ("paid", "delivered"))]
S.push_rows = push_rows
S.session_begin = lambda: None
S.session_end = lambda: None


def lyudyna(uid, name, seen=OLD, tag=None, magnet=False, role="client"):
    DB["users"][uid] = {"user_id": uid, "username": "u" + str(uid), "first_name": name, "last_name": None,
                        "role": role, "source_tag": tag, "last_seen_at": seen,
                        "got_magnet_at": seen if magnet else None}


def kupivlia(uid, tier, status="delivered"):
    DB["purchases"]["X%s-%s" % (uid, tier)] = {"user_id": uid, "tier": tier, "status": status}


def podiia(uid, kind, payload=None, at=OLD):
    log_event(uid, kind, payload, at)


# Персонал: Yaro (адмін) з магнітом, Іра з гайдом
lyudyna(1, "Yaro", magnet=True); podiia(1, "magnet")
lyudyna(2, "Іра"); kupivlia(2, "t1")
# A
lyudyna(101, "Магніт", magnet=True); podiia(101, "magnet")
lyudyna(102, "Урок", tag="retush"); podiia(102, "retush_entry", {"tag": "retush"})
lyudyna(103, "Кабінет"); kv_set("kp:103:1.5:start", "1")
lyudyna(108, "Не оплатила", magnet=True); podiia(108, "magnet"); kupivlia(108, "k12z", "new")
lyudyna(111, "Стопка", magnet=True); podiia(111, "message", {"text": "Дякую, стопка фото гарна"})
lyudyna(113, "Повернулась", seen=OLD, magnet=True)
kv_set("blocked:113", "403"); DB["kv_at"]["blocked:113"] = OLD - timedelta(days=1)
# B
lyudyna(104, "Гість МК", tag="mk_link"); kupivlia(104, "t1"); kupivlia(104, "k12")
lyudyna(105, "Курс, заблокувала"); kupivlia(105, "k12z", "paid")
lyudyna(107, "Курс і гайд"); kupivlia(107, "t1"); kupivlia(107, "k1")
kupivlia(120, "k12"); podiia(120, "give_manual", {"by": 1, "ok": True})      # видача /vydaty, рядка users нема
# G
lyudyna(106, "Гайд", magnet=True); kupivlia(106, "t1")
lyudyna(118, "Гайд свіжий", seen=FRESH); kupivlia(118, "t1")
# решта і виключення
lyudyna(109, "Лише старт"); podiia(109, "start", {"tag": ""})
lyudyna(110, "Стоп", magnet=True); podiia(110, "message", {"text": "Стоп, не треба"})
lyudyna(117, "Відписка", tag="retush"); podiia(117, "message", {"text": "Відпишіть мене будь ласка"})
lyudyna(112, "Заблокувала", magnet=True)
kv_set("blocked:112", "403"); DB["kv_at"]["blocked:112"] = OLD + timedelta(days=1)
lyudyna(114, "Свіжа", magnet=True); podiia(114, "magnet", at=FRESH)
lyudyna(115, "Вже мала", magnet=True); kv_set("push1:115", "ok A")
lyudyna(901, "Тест", magnet=True)
lyudyna(902, "Друг"); kupivlia(902, "k12")


def msg(text, uid):
    return app.post("/sekret", json={"message": {"message_id": 1, "chat": {"id": uid, "type": "private"},
                    "from": {"id": uid, "first_name": "X", "username": "u" + str(uid)}, "text": text}})


def sent(method="sendMessage", chat=None):
    return [p for m, p in VYKLYKY if m == method and (chat is None or p.get("chat_id") == chat)]


def lyudyam():
    """Усі відправки не персоналу (1 і 2)."""
    return [(m, p) for m, p in VYKLYKY if p.get("chat_id") not in (1, 2)]


def ids(lst):
    return sorted(p["id"] for p in lst)


T = bot.push1_texts()

# 1. Тексти з push1.txt і змінних
ok("тексти: A і B є, без ЗАГЛУШКА", T["A"] and T["B"] and bot.PUSH_STUB not in T["A"] + T["B"])
ok("тексти: A і B починаються «Привіт, це Іра♥️»", T["A"].startswith("Привіт, це Іра♥️") and T["B"].startswith("Привіт, це Іра♥️"))
ok("тексти: B закінчується «Легкого вам навчання🫂»", T["B"].endswith("Легкого вам навчання🫂"), T["B"][-30:])
ok("тексти: коментар до першої секції не потрапив", "Розсилка push1" not in T["A"] + T["B"] + T["G"])
ok("тексти: G порожній, кнопка «Канал «для своїх»»", T["G"] == "" and T["KNOPKA"] == "Канал «для своїх»")
ok("кнопка: інвайт зі змінної", bot.push1_link(T) == (INVITE, "інвайт push1"))
os.environ.pop("PUSH1_URL")
ok("кнопка: без PUSH1_URL це CHANNEL_URL", bot.push1_link(bot.push1_texts())[0] == "https://t.me/test_kanal")
os.environ["PUSH1_URL"] = INVITE
os.environ["PUSH1_A"] = "Рядок 1\\nРядок 2"
ok("змінна PUSH1_A перебиває файл, \\n = новий рядок", bot.push1_texts()["A"] == "Рядок 1\nРядок 2")
os.environ["PUSH1_A"] = "-"
ok("змінна «-» = порожньо", bot.push1_texts()["A"] == "")
os.environ.pop("PUSH1_A")
_f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_push1_test.txt")
open(_f, "w", encoding="utf-8").write("коментар\n[A] не секція\n[a]\n\nрядок\n[ЩОСЬ]\n\n[B]\nб\n")
_t = bot.push1_texts(_f)
os.remove(_f)
ok("розбір: секція без регістру, чужі дужки це текст", _t["A"] == "рядок\n[ЩОСЬ]" and _t["B"] == "б", str(_t))
ok("заглушка: go не шле", bot.push1_problems(dict(T, A="ЗАГЛУШКА A")) == ["текст A ще ЗАГЛУШКА"])
ok("готові тексти: перешкод нема", bot.push1_problems(T) == [])

# 2. Сегменти
SG = bot.push1_segments()
ok("A: магніт, урок, кабінет, неоплачена заявка, «стопка», повернулась",
   ids(SG["seg"]["A"]) == [101, 102, 103, 108, 111, 113], str(ids(SG["seg"]["A"])))
ok("B: МК, оплата, курс з гайдом, /vydaty без рядка users", ids(SG["seg"]["B"]) == [104, 105, 107, 120],
   str(ids(SG["seg"]["B"])))
ok("G: гайд без курсу", ids(SG["seg"]["G"]) == [106], str(ids(SG["seg"]["G"])))
sk = {w: ids(v) for w, v in SG["skip"].items()}
ok("не шлемо: персонал (адмін, Іра)", sk["персонал"] == [1, 2], str(sk))
ok("не шлемо: PUSH_SKIP_IDS", sk["вручну (PUSH_SKIP_IDS)"] == [901, 902])
ok("не шлемо: push1 уже був", sk["push1 уже був"] == [115])
ok("не шлемо: заблокували (403 пізніше за візит)", sk["заблокували бота"] == [112])
ok("не шлемо: «стоп» і відписка", sk["писали «стоп»"] == [110, 117])
ok("не шлемо: бот писав за 24 год (подія чи візит)", sk["бот писав за 24 год"] == [114, 118])
ok("решта: лише /start", SG["rest"] == 1)
ok("стоп-слова", all(bot.PUSH_STOP_RE.search(x) for x in ("STOP", "/stop", "стоп", "Не пишіть мені", "отпишите"))
   and not any(bot.PUSH_STOP_RE.search(x) for x in ("стопка", "автостоп", "пишіть сюди", "відповідь")))

# 3. /push1 від адміна: перегляд лише йому
VYKLYKY.clear()
msg("/push1", 1)
ok("перегляд: усе лише адміну (не Ірі, не людям)", VYKLYKY and all(p.get("chat_id") == 1 for _, p in VYKLYKY),
   str([p.get("chat_id") for _, p in VYKLYKY]))
txt = [p.get("text") or "" for p in sent(chat=1)]
s0 = txt[0] if txt else ""
for frag in ("нікому з людей нічого не надіслано",
             "A, магніт чи урок 1.5, без покупок: 6 (магніт у 4, урок 1.5 у 2, з них відкрили урок у кабінеті 1)",
             "B, мають курс: 4", "G, гайд без курсу: 1 (тексту G нема: їм не шлемо)", "Разом піде: 10",
             "Не шлемо: персонал 2, вручну (PUSH_SKIP_IDS) 2, push1 уже був 1, заблокували бота 1, "
             "писали «стоп» 2, бот писав за 24 год 2",
             "Решта в базі (лише /start, без магніту, уроку й покупок): 1",
             "Кнопка «Канал «для своїх»»: " + INVITE + " (інвайт push1)", "Тексти: готові",
             "Магніт, @u101, id 101", "Не шлемо, бот писав за 24 год:", "Нижче тексти так, як їх побачать люди: A, потім B."):
    ok("перегляд: «" + frag[:50] + "»", frag in s0, s0 if frag not in s0 else "")
kb_ok = [p for p in sent(chat=1) if (p.get("reply_markup") or {}).get("inline_keyboard")
         == [[{"text": "Канал «для своїх»", "url": INVITE}]]]
ok("перегляд: текст A і текст B з кнопкою, дослівно", [p["text"] for p in kb_ok] == [T["A"], T["B"]])
ok("перегляд: kv push1 нікому не поставлено", [k for k in DB["kv"] if k.startswith("push1:")] == ["push1:115"])

# 4. /push1 від не персоналу: не перегляд (звичайне повідомлення персоналу)
VYKLYKY.clear()
msg("/push1 go", 101)
ok("не персонал: нікому текстів push1", not any(T["A"] == p.get("text") or T["B"] == p.get("text")
                                                for _, p in VYKLYKY))
ok("не персонал: перегляду нема", not any("push1, перегляд" in (p.get("text") or "") for _, p in VYKLYKY))
ok("не персонал: заявок push1 нема", not [k for k in DB["kv"] if k.startswith("push1:") and k != "push1:115"])
DB["events"] = [e for e in DB["events"] if not (e[0] == 101 and e[1] == "message")]
lyudyna(101, "Магніт", magnet=True)              # його «/push1 go» зробив би його свіжим: повертаємо як було

# 5. go поза вікном, із заглушкою, без бази, зайнятий: нікому
VYKLYKY.clear()
for h in (9, 20, 23):
    HOUR[:] = [h]
    msg("/push1 go", 1)
ok("поза 10:00–20:00: відмова тричі, людям нічого", not lyudyam()
   and sum("шле лише 10:00–20:00, нікому не надіслано" in (p.get("text") or "") for p in sent(chat=1)) == 3)
HOUR[:] = [12]
os.environ["PUSH1_B"] = "ЗАГЛУШКА B"
VYKLYKY.clear()
msg("/push1 go", 1)
ok("заглушка: відмова, людям нічого", not lyudyam() and any("текст B ще ЗАГЛУШКА" in (p.get("text") or "")
                                                            for p in sent(chat=1)))
os.environ.pop("PUSH1_B")
S.ON = False
VYKLYKY.clear()
msg("/push1 go", 1)
ok("без бази: відмова", not lyudyam() and any("Бази нема" in (p.get("text") or "") for p in sent(chat=1)))
VYKLYKY.clear()
msg("/push1", 1)
ok("без бази: перегляд каже і показує тексти", any("База вимкнена" in (p.get("text") or "") for p in sent(chat=1))
   and [p.get("text") for p in sent(chat=1)][-2:] == [T["A"], T["B"]])
S.ON = True
bot._push_busy.acquire()
VYKLYKY.clear()
msg("/push1 go", 1)
bot._push_busy.release()
ok("уже йде: відмова", not lyudyam() and any("уже йде" in (p.get("text") or "") for p in sent(chat=1)))

# 6. go у вікні: раз на людину, A текст A, B текст B, G без тексту ні, ~1 на секунду
VYKLYKY.clear()
SNY.clear()
msg("/push1 go", 1)
dost = {}
for m, p in lyudyam():
    if m == "sendMessage":
        dost.setdefault(p["chat_id"], []).append(p)
ok("go: кому пішло (з повтором після 429 у 102)", sorted(dost) == [101, 102, 103, 104, 105, 107, 108, 111, 113, 120],
   str(sorted(dost)))
ok("go: 429 повторено, решта рівно по одному", len(dost.get(102, [])) == 2
   and all(len(v) == 1 for k, v in dost.items() if k != 102))
ok("go: A отримали текст A", all(dost[u][-1]["text"] == T["A"] for u in (101, 102, 103, 108, 111, 113)))
ok("go: B отримали текст B", all(dost[u][-1]["text"] == T["B"] for u in (104, 105, 107, 120)))
ok("go: кнопка-інвайт у кожного", all(dost[u][-1]["reply_markup"] == {"inline_keyboard": [[{"text": "Канал «для своїх»",
                                                                                              "url": INVITE}]]}
                                      for u in dost))
ok("go: G, виключені й персонал нічого", not any(u in dost for u in (2, 106, 110, 112, 114, 115, 117, 118, 901, 902, 109)))
ok("go: пауза 1 с між людьми і 2.3 с на 429", SNY.count(bot.PUSH_PAUSE) == 9 and 2.3 in SNY, str(SNY))
ok("go: kv push1 по людині", all(DB["kv"].get("push1:%s" % u) == "ok A" for u in (101, 102, 103, 108, 111, 113))
   and DB["kv"]["push1:104"] == "ok B" and DB["kv"]["push1:120"] == "ok B"
   and DB["kv"]["push1:105"] == "403 B" and DB["kv"]["push1:107"] == "err B")
ok("go: 403 позначає заблокованою", "blocked:105" in DB["kv"] and "Forbidden" in DB["kv"]["blocked:105"])
ev = [e for e in DB["events"] if e[1] == "push1"]
ok("go: подія push1 на кожного з сегментом", sorted(e[0] for e in ev) == sorted(dost)
   and all(e[2]["seg"] in ("A", "B") for e in ev)
   and [e[2]["ok"] for e in ev if e[0] in (105, 107)] == [False, False])
ok("go: подія push1_go і push1_run від адміна", any(e[0] == 1 and e[1] == "push1_go" for e in DB["events"])
   and any(e[0] == 1 and e[1] == "push1_run" and e[2]["blocked"] == 1 for e in DB["events"]))
zv = [p["text"] for p in sent(chat=1)]
ok("go: звіт адміну", any(z.startswith("push1 готово: надіслано 8 (A 6, B 2).") for z in zv), str(zv))
ok("go: у звіті 403 і помилка", any("Заблокували бота: 1 (id 105)" in z and "107: Bad Request: chat not found" in z
                                     for z in zv))
ok("go: «Почала push1» з числами", any(z.startswith("Почала push1: A 6, B 4, разом 10") for z in zv), str(zv))
ok("go: Ірі нічого", not sent(chat=2))

# 7. Другий go: повторів нема
VYKLYKY.clear()
msg("/push1 go", 1)
ok("другий go: людям нічого", not lyudyam())
ok("другий go: «нікому слати»", any("нікому слати" in (p.get("text") or "") for p in sent(chat=1)))
SG2 = bot.push1_segments()
ok("після go: усі 10 у «push1 уже був»", ids(SG2["skip"]["push1 уже був"]) == [101, 102, 103, 104, 105, 107, 108,
                                                                                111, 113, 115, 120])

# 8. Вікно закрилось посередині: решта чекає наступного go
for u in (130, 131, 132):
    lyudyna(u, "Нова" + str(u), magnet=True)
VYKLYKY.clear()
HOUR[:] = [19, 19, 20]
msg("/push1 go", 1)
HOUR[:] = [12]
ok("вікно: пішло лише першій", [p["chat_id"] for m, p in lyudyam()] == [130], str([p["chat_id"] for m, p in lyudyam()]))
ok("вікно: решті заявки не поставлено", "push1:131" not in DB["kv"] and "push1:132" not in DB["kv"])
ok("вікно: звіт «не встигла до 20:00: 2»", any("Не встигла до 20:00 за Києвом: 2" in (p.get("text") or "")
                                               for p in sent(chat=1)))
VYKLYKY.clear()
msg("/push1 go", 1)
ok("наступний go дошле решту, без повторів", sorted(p["chat_id"] for m, p in lyudyam()) == [131, 132])

# 9. Відповідь персоналу = бот писав людині (24 год); 403 будь-де = позначка; канал не позначаємо
lyudyna(15050, "Питала", magnet=True)
ok("staff_reply: до відповіді людина в A", 15050 in ids(bot.push1_segments()["seg"]["A"]))
bot.staff_reply({"message_id": 5, "from": {"id": 2}, "reply_to_message": {"message_id": 77, "text":
                 "Повідомлення в боті від Питала, @u15050, id 15050:\nа де урок?"}}, 2)
ok("staff_reply: подія і людина свіжа", any(e[0] == 15050 and e[1] == "staff_reply" for e in DB["events"])
   and 15050 in ids(bot.push1_segments()["skip"]["бот писав за 24 год"]))
bot.api("sendDocument", chat_id=140, document="X")
bot.api("sendMessage", chat_id=-100500, text="x")
ok("403 будь-де: blocked:140 є, канал без позначки", "blocked:140" in DB["kv"] and "blocked:-100500" not in DB["kv"])
DB["kv_at"]["blocked:140"] = NOW - timedelta(hours=1)     # 403 годину тому (годинник Windows грубий, без нічиїх)
lyudyna(140, "Заблокувала давно", magnet=True)
ok("403 будь-де: у сегментах заблокована", 140 in ids(bot.push1_segments()["skip"]["заблокували бота"]))
touch_user({"id": 140, "first_name": "Повернулась"})
ok("повернулась (написала боту після 403): не заблокована, але свіжа",
   140 in ids(bot.push1_segments()["skip"]["бот писав за 24 год"]))

# 10. Сторінка /push1/<S>: лише читання, поіменно
lyudyna(160, "Нова для сторінки", magnet=True)
VYKLYKY.clear()
r = app.get("/push1/sekret")
body = r.get_data(as_text=True)
ok("сторінка: 200, числа, хто і тексти", r.status_code == 200 and "B, мають курс:" in body and "Хто A:" in body
   and "Не шлемо, писали «стоп»:" in body and "Текст B:" in body and "Легкого вам навчання" in body)
ok("сторінка: нікому нічого не шле", not VYKLYKY)
ok("сторінка без секрету: 404", app.get("/push1/inshe").status_code == 404)

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
