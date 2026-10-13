#!/usr/bin/env python3
"""
Розсилка push1 (13.10) БЕЗ мережі і бази: кожному той безкоштовний подарунок, якого ще нема. G1 (брали урок
1.5, схем нема): PDF схем з підписом G1 і кнопкою каналу, схеми позначено. G2 (схеми без уроку 1.5 і без
курсу): текст G2 з кнопками уроку в кабінеті й каналу. Хто має і схеми, і урок (чи курс), нічого. Виключення
(персонал, PUSH_SKIP_IDS, push1 уже був, 403, «стоп», бот писав за 24 год); /push1 перегляд лише тому, хто
питає, обидва повідомлення так, як їх побачать люди; /push1 go раз на людину, ~1 на секунду, лише 10:00–20:00
за Києвом, 403 = позначка blocked, подарунок схем не дублює подарунок після уроку (заявка gift:<id>), звіт
тому, хто запустив; сторінка /push1/<S>; тексти з push1.txt і змінних. Нікому з людей тут нічого не йде:
requests.post підставний. Запуск: python -B test_push1.py
"""
import os, sys
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

INVITE = "https://t.me/+TESTinvite"
MAGNIT = "https://test/magnit.pdf"
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "IRA_ID": "2",
                   "NO_THREADS": "1", "NOTIFY_IDS": "1,2", "CHANNEL_URL": "https://t.me/test_kanal",
                   "PUSH_SKIP_IDS": "901, 902", "PUSH1_URL": INVITE, "MAGNET_URL": MAGNIT,
                   "KABINET_URL": "https://kab.test", "KABINET_KEY": "k"})
for _k in ("DATABASE_URL", "PUSH1_G1", "PUSH1_G2", "PUSH1_KNOPKA", "PUSH1_UROK", "LEAD_IDS"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []
ZBII = {105, 140, -100500}                     # 403: заблокували бота
POMYLKA = {113}                                # 400: інша причина
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
KAB = []
bot.kabinet_mist.push_user = lambda uid: KAB.append(uid)
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


def mark_magnet(uid):
    if uid in DB["users"] and not DB["users"][uid].get("got_magnet_at"):
        DB["users"][uid]["got_magnet_at"] = datetime.now(timezone.utc)


def fake_q(sql, args=(), fetch=None):
    if sql.startswith("select updated_at from kv where k = %s"):
        at = DB["kv_at"].get(args[0])
        return {"updated_at": at} if at else None
    raise AssertionError("неочікуваний запит: " + sql[:60])


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
            "ev_magnet": any(e[1] == "magnet" for e in evs),
            "ev_lesson": any(e[1] in ("retush_entry", "lesson_gift") for e in evs),
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
S.q = fake_q
S.touch_user = touch_user
S.mark_magnet = mark_magnet
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


def urok(uid, at=OLD):
    podiia(uid, "retush_entry", {"tag": "retush"}, at)


# Персонал: Yaro (адмін) з магнітом, Іра з гайдом
lyudyna(1, "Yaro", magnet=True); podiia(1, "magnet")
lyudyna(2, "Іра"); kupivlia(2, "t1")
# G1: урок 1.5 без схем
lyudyna(102, "Урок", tag="retush"); urok(102)
lyudyna(103, "Кабінет"); kv_set("kp:103:1.5:start", "1")
lyudyna(121, "Урок і гайд", tag="retush"); urok(121); kupivlia(121, "t1")
lyudyna(122, "Урок і курс", tag="retush"); urok(122); kupivlia(122, "k12")
lyudyna(123, "Подарунок не дійшов", tag="retush"); urok(123)
kv_set("gift:123", "1"); DB["kv_at"]["gift:123"] = OLD                   # заявка старa, схем нема: не дійшов
lyudyna(124, "Подарунок саме йде", tag="retush"); urok(124)
kv_set("gift:124", "1"); DB["kv_at"]["gift:124"] = NOW - timedelta(minutes=5)
# G2: схеми без уроку і без курсу
lyudyna(101, "Магніт", magnet=True); podiia(101, "magnet")
lyudyna(105, "Схеми, заблокує", magnet=True)
lyudyna(106, "Схеми і гайд", magnet=True); kupivlia(106, "t1")
lyudyna(108, "Не оплатила", magnet=True); podiia(108, "magnet"); kupivlia(108, "k12z", "new")
lyudyna(111, "Стопка", magnet=True); podiia(111, "message", {"text": "Дякую, стопка фото гарна"})
lyudyna(113, "Повернулась", seen=OLD, magnet=True)
kv_set("blocked:113", "403"); DB["kv_at"]["blocked:113"] = OLD - timedelta(days=1)
# обидва: поки нічого
lyudyna(126, "Обидва", magnet=True); urok(126)
lyudyna(107, "Курс і схеми", magnet=True); kupivlia(107, "k1")
# ні схем, ні уроку
lyudyna(104, "Гість МК", tag="mk_link"); kupivlia(104, "t1"); kupivlia(104, "k12")
lyudyna(109, "Лише старт"); podiia(109, "start", {"tag": ""})
kupivlia(120, "k12"); podiia(120, "give_manual", {"by": 1, "ok": True})      # видача /vydaty, рядка users нема
# виключення
lyudyna(110, "Стоп", magnet=True); podiia(110, "message", {"text": "Стоп, не треба"})
lyudyna(117, "Відписка", tag="retush"); urok(117); podiia(117, "message", {"text": "Відпишіть мене будь ласка"})
lyudyna(112, "Заблокувала", magnet=True)
kv_set("blocked:112", "403"); DB["kv_at"]["blocked:112"] = OLD + timedelta(days=1)
lyudyna(114, "Свіжа", magnet=True); podiia(114, "magnet", at=FRESH)
lyudyna(118, "Урок свіжий", seen=FRESH, tag="retush"); urok(118, FRESH)
lyudyna(115, "Вже мала", magnet=True); kv_set("push1:115", "ok G2")
lyudyna(901, "Тест", magnet=True)
lyudyna(902, "Друг", tag="retush"); urok(902)


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
KB_G1 = {"inline_keyboard": [[{"text": "Канал «для своїх»", "url": INVITE}]]}
KB_G2 = {"inline_keyboard": [[{"text": "Відкрити урок", "web_app": {"url": "https://kab.test/?p=1.5"}},
                              {"text": "Канал «для своїх»", "url": INVITE}]]}

# 1. Тексти з push1.txt і змінних
ok("тексти: G1 і G2 є, без ЗАГЛУШКА", T["G1"] and T["G2"] and bot.PUSH_STUB not in T["G1"] + T["G2"])
ok("тексти: G1 дослівно", T["G1"] == ("Привіт, я Іра♥️ Дарую вам свої 3 робочі схеми світла.\n\n"
                                       "Все, що лишається, скопіювати їх і почати покращувати своє портфоліо.\n\n"
                                       "А також підписуйтесь на мій тг канал, там розповідаю свою історію🫶🏻"))
ok("тексти: G2 дослівно", T["G2"] == ("Привіт, я Іра♥️ Дарую вам свій урок ретуші.\n\n"
                                       "«Чистка шкіри без втрати текстури», 12 хвилин. Можете дивитись тоді, коли вам "
                                       "буде зручно.\n\n"
                                       "А також підписуйтесь на мій тг канал, там розповідаю свою історію🫶🏻"))
ok("тексти: старих A і B нема, коментар до першої секції не потрапив", set(T) == {"G1", "G2", "KNOPKA", "UROK", "URL"}
   and "Розсилка push1" not in T["G1"] + T["G2"])
ok("тексти: кнопки «Канал «для своїх»» і «Відкрити урок»", T["KNOPKA"] == "Канал «для своїх»" and T["UROK"] == "Відкрити урок")
ok("кнопка каналу: інвайт зі змінної", bot.push1_link(T) == (INVITE, "інвайт push1"))
os.environ.pop("PUSH1_URL")
ok("кнопка каналу: без PUSH1_URL це CHANNEL_URL", bot.push1_link(bot.push1_texts())[0] == "https://t.me/test_kanal")
os.environ["PUSH1_URL"] = INVITE
ok("кнопки: G1 лише канал, G2 урок поруч із каналом", bot.push1_kb(T, "G1") == KB_G1 and bot.push1_kb(T, "G2") == KB_G2)
os.environ["PUSH1_G1"] = "Рядок 1\\nРядок 2"
ok("змінна PUSH1_G1 перебиває файл, \\n = новий рядок", bot.push1_texts()["G1"] == "Рядок 1\nРядок 2")
os.environ["PUSH1_G1"] = "-"
ok("змінна «-» = порожньо", bot.push1_texts()["G1"] == "")
os.environ.pop("PUSH1_G1")
_f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_push1_test.txt")
open(_f, "w", encoding="utf-8").write("коментар\n[G1] не секція\n[g1]\n\nрядок\n[ЩОСЬ]\n\n[G2]\nб\n[A]\nстаре\n")
_t = bot.push1_texts(_f)
os.remove(_f)
ok("розбір: секція без регістру, чужі дужки це текст", _t["G1"] == "рядок\n[ЩОСЬ]" and _t["G2"] == "б\n[A]\nстаре", str(_t))
ok("заглушка: go не шле", bot.push1_problems(dict(T, G2="ЗАГЛУШКА G2")) == ["текст G2 ще ЗАГЛУШКА"])
ok("G1 довший за підпис під файлом: go не шле", bot.push1_problems(dict(T, G1="я" * 1025))
   == ["текст G1 довший за 1024 знаків"])
ok("готові тексти: перешкод нема", bot.push1_problems(T) == [])
_mu = bot.MAGNET_URL
bot.MAGNET_URL = ""
bot._REF_CACHE.clear()
ok("без PDF схем: go не шле G1", "нема PDF схем (магніту) для G1" in bot.push1_problems(T))
bot.MAGNET_URL = _mu
bot._REF_CACHE.clear()

# 2. Сегменти
SG = bot.push1_segments()
ok("G1: урок у боті, урок у кабінеті, з гайдом, з курсом, подарунок не дійшов, подарунок саме йде",
   ids(SG["seg"]["G1"]) == [102, 103, 121, 122, 123, 124], str(ids(SG["seg"]["G1"])))
ok("G2: схеми без уроку і курсу (з гайдом теж, неоплачена заявка не рахується)",
   ids(SG["seg"]["G2"]) == [101, 105, 106, 108, 111, 113], str(ids(SG["seg"]["G2"])))
sk = {w: ids(v) for w, v in SG["skip"].items()}
ok("не шлемо: персонал (адмін)", sk["персонал"] == [1], str(sk))
ok("не шлемо: PUSH_SKIP_IDS", sk["вручну (PUSH_SKIP_IDS)"] == [901, 902])
ok("не шлемо: push1 уже був", sk["push1 уже був"] == [115])
ok("не шлемо: заблокували (403 пізніше за візит)", sk["заблокували бота"] == [112])
ok("не шлемо: «стоп» і відписка", sk["писали «стоп»"] == [110, 117])
ok("не шлемо: бот писав за 24 год (подія чи візит)", sk["бот писав за 24 год"] == [114, 118])
ok("обидва (схеми й урок чи курс): 2, поки нічого", SG["both"] == 2, str(SG["both"]))
ok("ні схем, ні уроку: Іра, гість МК, лише старт, /vydaty без users", SG["none"] == 4, str(SG["none"]))
ok("покупки видно в G1", [p["buys"] for p in SG["seg"]["G1"] if p["id"] in (121, 122)] == [["t1"], ["k12"]])
ok("стоп-слова", all(bot.PUSH_STOP_RE.search(x) for x in ("STOP", "/stop", "стоп", "Не пишіть мені", "отпишите"))
   and not any(bot.PUSH_STOP_RE.search(x) for x in ("стопка", "автостоп", "пишіть сюди", "відповідь")))

# 3. /push1 від адміна: перегляд лише йому, обидва повідомлення як у людей
VYKLYKY.clear()
msg("/push1", 1)
ok("перегляд: усе лише адміну (не Ірі, не людям)", VYKLYKY and all(p.get("chat_id") == 1 for _, p in VYKLYKY),
   str([p.get("chat_id") for _, p in VYKLYKY]))
txt = [p.get("text") or "" for p in sent(chat=1)]
s0 = txt[0] if txt else ""
for frag in ("нікому з людей нічого не надіслано",
             "G1, брали урок 1.5, схем нема: дарую 3 схеми (PDF): 6 (з них з покупками 2)",
             "G2, брали схеми, уроку 1.5 не мали: дарую урок: 6 (з них з покупками 1)", "Разом піде: 12",
             "Не шлемо: персонал 1, вручну (PUSH_SKIP_IDS) 2, push1 уже був 1, заблокували бота 1, "
             "писали «стоп» 2, бот писав за 24 год 2",
             "Мають і схеми, і урок 1.5 (чи курс): 2, їм поки нічого.",
             "Ні схем, ні уроку 1.5 (лише /start чи лише покупки): 4, не шлемо.",
             "Кнопка «Канал «для своїх»» у G1 і G2: " + INVITE + " (інвайт push1)",
             "Кнопка «Відкрити урок» у G2: https://kab.test/?p=1.5", "Тексти: готові",
             "Урок і курс, @u122, id 122 (купила: k12)", "Не шлемо, бот писав за 24 год:",
             "Нижче повідомлення так, як їх побачать люди: G1 (PDF схем з підписом), потім G2 (кнопки уроку й каналу)."):
    ok("перегляд: «" + frag[:50] + "»", frag in s0, s0 if frag not in s0 else "")
d1 = sent("sendDocument", chat=1)
ok("перегляд: G1 = PDF схем з підписом G1 і кнопкою каналу",
   len(d1) == 1 and d1[0]["document"] == MAGNIT and d1[0]["caption"] == T["G1"] and d1[0]["reply_markup"] == KB_G1)
g2 = [p for p in sent(chat=1) if p.get("text") == T["G2"]]
ok("перегляд: G2 = текст з кнопками уроку й каналу", len(g2) == 1 and g2[0]["reply_markup"] == KB_G2)
ok("перегляд: kv push1 і схем нікому не поставлено", [k for k in DB["kv"] if k.startswith("push1:")] == ["push1:115"]
   and not DB["users"][102].get("got_magnet_at"))

# 4. /push1 від не персоналу: не перегляд (звичайне повідомлення персоналу)
VYKLYKY.clear()
msg("/push1 go", 101)
ok("не персонал: нікому подарунків push1", not sent("sendDocument") and not any(T["G2"] == p.get("text")
                                                                                for _, p in VYKLYKY))
ok("не персонал: перегляду нема", not any("push1, перегляд" in (p.get("text") or "") for _, p in VYKLYKY))
ok("не персонал: заявок push1 нема", not [k for k in DB["kv"] if k.startswith("push1:") and k != "push1:115"])
DB["events"] = [e for e in DB["events"] if not (e[0] == 101 and e[1] == "message")]
lyudyna(101, "Магніт", magnet=True)              # її «/push1 go» зробив би її свіжою: повертаємо як було

# 5. go поза вікном, із заглушкою, без бази, зайнятий: нікому
VYKLYKY.clear()
for h in (9, 20, 23):
    HOUR[:] = [h]
    msg("/push1 go", 1)
ok("поза 10:00–20:00: відмова тричі, людям нічого", not lyudyam()
   and sum("шле лише 10:00–20:00, нікому не надіслано" in (p.get("text") or "") for p in sent(chat=1)) == 3)
HOUR[:] = [12]
os.environ["PUSH1_G2"] = "ЗАГЛУШКА G2"
VYKLYKY.clear()
msg("/push1 go", 1)
ok("заглушка: відмова, людям нічого", not lyudyam() and any("текст G2 ще ЗАГЛУШКА" in (p.get("text") or "")
                                                            for p in sent(chat=1)))
os.environ.pop("PUSH1_G2")
S.ON = False
VYKLYKY.clear()
msg("/push1 go", 1)
ok("без бази: відмова", not lyudyam() and any("Бази нема" in (p.get("text") or "") for p in sent(chat=1)))
VYKLYKY.clear()
msg("/push1", 1)
ok("без бази: перегляд каже і показує обидва повідомлення", any("База вимкнена" in (p.get("text") or "")
                                                               for p in sent(chat=1))
   and len(sent("sendDocument", chat=1)) == 1 and [p.get("text") for p in sent(chat=1)][-1] == T["G2"])
S.ON = True
bot._push_busy.acquire()
VYKLYKY.clear()
msg("/push1 go", 1)
bot._push_busy.release()
ok("уже йде: відмова", not lyudyam() and any("уже йде" in (p.get("text") or "") for p in sent(chat=1)))

# 6. go у вікні: раз на людину, G1 PDF з підписом, G2 текст з уроком, ~1 на секунду
VYKLYKY.clear()
SNY.clear()
KAB.clear()
msg("/push1 go", 1)
dost = {}
for m, p in lyudyam():
    dost.setdefault(p["chat_id"], []).append((m, p))
ok("go: кому пішло (з повтором після 429 у 102)",
   sorted(dost) == [101, 102, 103, 105, 106, 108, 111, 113, 121, 122, 123], str(sorted(dost)))
ok("go: 429 повторено, решта рівно по одному", len(dost.get(102, [])) == 2
   and all(len(v) == 1 for k, v in dost.items() if k != 102))
ok("go: G1 отримали PDF схем з підписом G1 і кнопкою каналу",
   all(dost[u][-1][0] == "sendDocument" and dost[u][-1][1]["document"] == MAGNIT
       and dost[u][-1][1]["caption"] == T["G1"] and dost[u][-1][1]["reply_markup"] == KB_G1
       for u in (102, 103, 121, 122, 123)))
ok("go: G2 отримали текст G2 з кнопками уроку й каналу",
   all(dost[u][-1][0] == "sendMessage" and dost[u][-1][1]["text"] == T["G2"] and dost[u][-1][1]["reply_markup"] == KB_G2
       for u in (101, 105, 106, 108, 111, 113)))
ok("go: подарунок саме йде (свіжа заявка gift): 124 нічого", 124 not in dost and "push1:124" not in DB["kv"])
ok("go: обидва, виключені й персонал нічого", not any(u in dost for u in (2, 104, 107, 109, 110, 112, 114, 115, 117,
                                                                          118, 120, 126, 901, 902)))
ok("go: пауза 1 с між людьми і 2.3 с на 429", SNY.count(bot.PUSH_PAUSE) == 10 and 2.3 in SNY, str(SNY))
ok("go: kv push1 по людині", all(DB["kv"].get("push1:%s" % u) == "ok G1" for u in (102, 103, 121, 122, 123))
   and all(DB["kv"].get("push1:%s" % u) == "ok G2" for u in (101, 106, 108, 111))
   and DB["kv"]["push1:105"] == "403 G2" and DB["kv"]["push1:113"] == "err G2")
ok("go: G1 тепер мають схеми (подія magnet via push1), заявка gift стоїть",
   all(DB["users"][u].get("got_magnet_at") for u in (102, 103, 121, 122, 123))
   and sorted(e[0] for e in DB["events"] if e[1] == "magnet" and (e[2] or {}).get("via") == "push1")
   == [102, 103, 121, 122, 123] and all(("gift:%s" % u) in DB["kv"] for u in (102, 103, 121, 122)))
ok("go: G2 подія lesson_gift і людина в кабінеті до кнопки",
   sorted(e[0] for e in DB["events"] if e[1] == "lesson_gift") == [101, 106, 108, 111]
   and all(u in KAB for u in (101, 105, 106, 108, 111, 113)))
ok("go: 403 позначає заблокованою", "blocked:105" in DB["kv"] and "Forbidden" in DB["kv"]["blocked:105"])
ev = [e for e in DB["events"] if e[1] == "push1"]
ok("go: подія push1 на кожного з сегментом", sorted(e[0] for e in ev) == sorted(dost)
   and all(e[2]["seg"] in ("G1", "G2") for e in ev)
   and [e[2]["ok"] for e in ev if e[0] in (105, 113)] == [False, False])
ok("go: подія push1_go і push1_run від адміна", any(e[0] == 1 and e[1] == "push1_go" for e in DB["events"])
   and any(e[0] == 1 and e[1] == "push1_run" and e[2]["blocked"] == 1 and e[2]["had"] == 1 for e in DB["events"]))
zv = [p["text"] for p in sent(chat=1)]
ok("go: звіт адміну", any(z.startswith("push1 готово: надіслано 9 (G1 5, G2 4).") for z in zv), str(zv))
ok("go: у звіті 403, помилка і подарунок, що саме йде",
   any("Заблокували бота: 1 (id 105)" in z and "113: Bad Request: chat not found" in z
       and "G1 не надіслано, бо схеми вже є чи саме йдуть: 1 (124 подарунок схем саме йде)" in z for z in zv), str(zv))
ok("go: «Почала push1» з числами", any(z.startswith("Почала push1: G1 6, G2 6, разом 12") for z in zv), str(zv))
ok("go: Ірі нічого", not sent(chat=2) and not sent("sendDocument", chat=2))

# 7. Другий go: повторів нема; G1 після схем у «обидва»
VYKLYKY.clear()
msg("/push1 go", 1)
ok("другий go: людям нічого (124 досі «саме йде»)", not lyudyam(), str(lyudyam())[:200])
SG2 = bot.push1_segments()
ok("після go: G1 зі схемами і G2 з уроком у «обидва», 403 і помилка в «push1 уже був»",
   ids(SG2["skip"]["push1 уже був"]) == [105, 113, 115] and SG2["both"] == 2 + 5 + 4,
   str(ids(SG2["skip"]["push1 уже був"])) + " " + str(SG2["both"]))
DB["kv_at"]["gift:124"] = OLD                    # подарунок так і не дійшов: наступний go дарує
VYKLYKY.clear()
msg("/push1 go", 1)
ok("заявка gift застаріла, схем нема: наступний go дарує 124", [p["chat_id"] for m, p in lyudyam()] == [124]
   and DB["kv"].get("push1:124") == "ok G1")
lyudyna(125, "Схеми прийшли", tag="retush"); urok(125)
_gu = S.get_user
S.get_user = lambda uid: dict(_gu(uid) or {}, got_magnet_at=NOW) if uid == 125 else _gu(uid)
VYKLYKY.clear()
msg("/push1 go", 1)
S.get_user = _gu
ok("схеми прийшли між переглядом і go: 125 нічого, заявки push1 нема", not lyudyam() and "push1:125" not in DB["kv"]
   and any("125 уже мали схеми" in (p.get("text") or "") for p in sent(chat=1)))
DB["users"].pop(125)
DB["events"] = [e for e in DB["events"] if e[0] != 125]
DB["kv"].pop("gift:125", None)

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
ok("staff_reply: до відповіді людина в G2", 15050 in ids(bot.push1_segments()["seg"]["G2"]))
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
ok("сторінка: 200, числа, хто і тексти", r.status_code == 200 and "G2, брали схеми" in body and "Хто G2:" in body
   and "Не шлемо, писали «стоп»:" in body and "Текст G1 (підпис під PDF схем):" in body
   and "Дарую вам свій урок ретуші" in body)
ok("сторінка: нікому нічого не шле", not VYKLYKY)
ok("сторінка без секрету: 404", app.get("/push1/inshe").status_code == 404)

print("\nПАДІННЯ: %d" % len(PADINNIA) if PADINNIA else "\nВсе зелене")
sys.exit(1 if PADINNIA else 0)
