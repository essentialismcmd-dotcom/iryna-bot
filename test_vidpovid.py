#!/usr/bin/env python3
"""
Відповідь людині будь-чим (14.10) БЕЗ мережі і бази. Слово Yaro 14.10: «щоб можна було будь-що, будь-яке
повідомлення легко людині надіслати без переписування всього бота і передеплоювання».
Reply персоналу на сповіщення (текст, фото, стікер, голосове, кружок, альбом) -> копія людині + «Пішло»;
/do <id> і кнопка «Написати»: наступне повідомлення йде людині, режим знімається, /skasuvaty, година TTL;
людина з /do = звичайний CLIENT_TEXT; reply без id чи з кількома id нікуди не шле і каже про це;
кнопки «Написати» і «🎁 Подарунок» під сповіщеннями; подарунок без дубля; POST /nadislaty/<секрет>;
подія staff_reply {by, via, type, text}; 403 = blocked. Запуск: python -B test_vidpovid.py
"""
import os, sys, io, json as _json, time
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "555:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "MAGNET_URL": "MAGNIT", "NOTIFY_IDS": "1", "IRA_ID": "2", "IRA_ON": "1",
                   "START_PIC": "PIC_START", "CHANNEL_URL": "https://t.me/test_kanal"})
for _k in ("DATABASE_URL", "LEAD_IDS", "PUSH_SKIP_IDS"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []                  # (метод, параметри, message_id відповіді)
ZBII = {404404}               # 403: заблокувала бота
NEVIDOMI = {999999}           # 400: chat not found


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    method = url.rsplit("/", 1)[-1]
    p = dict(json or data or {})
    if files:
        p["_files"] = {k: v[0] for k, v in files.items()}
    mid = 1000 + len(VYKLYKY)
    VYKLYKY.append((method, p, mid))
    cid = p.get("chat_id")
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        pass
    if cid in ZBII:
        return _R({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
    if cid in NEVIDOMI:
        return _R({"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})
    if method == "getChat":
        return _R({"ok": True, "result": {"id": cid, "type": "private", "first_name": "Чат" + str(cid)}})
    if method == "sendPhoto":
        return _R({"ok": True, "result": {"message_id": mid, "photo": [{"file_id": "small"}, {"file_id": "BIG"}]}})
    if method == "sendDocument":
        return _R({"ok": True, "result": {"message_id": mid, "document": {"file_id": "DOC1"}}})
    if method == "copyMessages":
        return _R({"ok": True, "result": [{"message_id": mid}]})
    return _R({"ok": True, "result": {"message_id": mid}})


requests.post = fake_post
import bot
import store

# ---------- підставна база в памʼяті ----------
DB = {"kv": {}, "events": [], "users": {}}


def kv_set(k, v):
    DB["kv"][k] = str(v)


def kv_claim(k):
    if k in DB["kv"]:
        return False
    DB["kv"][k] = "1"
    return True


def log_event(uid, kind, payload=None):
    DB["events"].append((uid, kind, payload))


def touch_user(u, role="client", source_tag=None):
    uid = u.get("id")
    new = uid not in DB["users"]
    DB["users"][uid] = dict(DB["users"].get(uid, {}), user_id=uid, username=u.get("username"),
                            first_name=u.get("first_name"), last_name=u.get("last_name"))
    return dict(DB["users"][uid], is_new=new)


def mark_magnet(uid):
    if uid in DB["users"]:
        DB["users"][uid].setdefault("got_magnet_at", datetime.now(timezone.utc))


store.ON = True
store.q = lambda *a, **k: None
store.kv_get = lambda k, default=None: DB["kv"].get(k, default)
store.kv_set = kv_set
store.kv_claim = kv_claim
store.log_event = log_event
store.touch_user = touch_user
store.get_user = lambda uid: DB["users"].get(uid)
store.mark_magnet = mark_magnet
store.events_recent = lambda limit=200: [{"id": i, "created_at": "2026-10-14 10:00:00", "user_id": e[0],
                                          "kind": e[1], "payload": e[2]} for i, e in enumerate(DB["events"])][::-1]
bot.kabinet_mist.push_user = lambda uid: None
bot.bg = lambda fn, *a, **k: fn(*a, **k)          # фон синхронно: без гонок
bot._alb_spawn[0] = lambda fn, *a: None           # альбом флашимо руками (album_flush_all)
bot.time.sleep = lambda s: None

app = bot.app.test_client()
PADINNIA = []
OLIA, NINA = 777000, 777001
DB["users"][OLIA] = {"user_id": OLIA, "first_name": "Оля", "username": "olia"}
DB["users"][NINA] = {"user_id": NINA, "first_name": "Ніна", "username": None}
DB["users"][404404] = {"user_id": 404404, "first_name": "Блок", "username": "blk"}


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


MID = [100]


def msg(uid, chat=None, **kw):
    """Повідомлення в бот; повертає (виклики, message_id)."""
    MID[0] += 1
    m = dict({"message_id": MID[0], "chat": {"id": chat or uid, "type": "private"},
              "from": {"id": uid, "first_name": "S" + str(uid)}}, **kw)
    VYKLYKY.clear()
    app.post("/sekret", json={"message": m})
    return list(VYKLYKY), MID[0]


def cb(uid, data, mid=99):
    VYKLYKY.clear()
    app.post("/sekret", json={"callback_query": {"id": "c", "data": data, "from": {"id": uid},
                                                 "message": {"message_id": mid, "chat": {"id": uid}}}})
    return list(VYKLYKY)


def calls(vv, method, chat=None):
    return [p for m, p, _ in vv if m == method and (chat is None or p.get("chat_id") == chat)]


def says(vv, chat=1):
    return [p.get("text") or "" for p in calls(vv, "sendMessage", chat)]


def ev():
    return DB["events"][-1] if DB["events"] else None


def knopky(p):
    return [b.get("callback_data") for r in (p.get("reply_markup") or {}).get("inline_keyboard", []) for b in r]


BOTF = {"id": 555, "is_bot": True, "first_name": "Bot"}

# 1. Сповіщення про людину: кнопки «Написати» і «🎁 Подарунок» (лише тим, хто може /do), reply туди = людині
vv, _ = msg(OLIA, text="а де урок?", **{"from": {"id": OLIA, "first_name": "Оля", "username": "olia"}})
n1 = [(p, mid) for m, p, mid in vv if m == "sendMessage" and p.get("chat_id") == 1 and "а де урок?" in p.get("text", "")]
ok("сповіщення адміну з кнопками napys/podar", n1 and knopky(n1[0][0])[-2:] == ["napys:777000", "podar:777000"],
   str(n1)[:200])
n_ira = [p for p in calls(vv, "sendMessage", 2) if "а де урок?" in p.get("text", "")]
ok("Іра (не NOTIFY_IDS) отримує сповіщення без кнопок", n_ira and not knopky(n_ira[0]))
NOTIF = n1[0][1]

vv, mid = msg(1, text="Урок у кабінеті ♥️", reply_to_message={"message_id": NOTIF, "from": BOTF, "chat": {"id": 1}})
cp = calls(vv, "copyMessage")
ok("reply текстом -> copyMessage людині", len(cp) == 1 and cp[0]["chat_id"] == OLIA and cp[0]["from_chat_id"] == 1
   and cp[0]["message_id"] == mid, str(cp))
ack = [p for p in calls(vv, "sendMessage", 1) if p["text"].startswith("Пішло")]
ok("«Пішло: Оля, @olia» reply-ем на своє", ack and "Оля, @olia, id 777000" in ack[0]["text"]
   and ack[0].get("reply_parameters", {}).get("message_id") == mid, str(ack))
ok("подія staff_reply by/via/type/text", ev() == (OLIA, "staff_reply", {"by": 1, "via": "reply", "type": "текст",
                                                                       "text": "Урок у кабінеті ♥️"}), str(ev()))
ok("людині копія без клавіатури і без «переслано»", not calls(vv, "forwardMessage")
   and not any("reply_markup" in p for p in calls(vv, "copyMessage"))
   and not calls(vv, "sendMessage", OLIA))
ok("«Пішло» без постійної клавіатури", "reply_markup" not in ack[0])
ACK = [x for m, p, x in vv if m == "sendMessage" and p.get("text", "").startswith("Пішло")][0]

for kind, extra, label in (("photo", {"photo": [{"file_id": "a", "file_unique_id": "a"}], "caption": "ось"}, "фото"),
                           ("sticker", {"sticker": {"file_id": "st", "file_unique_id": "st"}}, "стікер"),
                           ("voice", {"voice": {"file_id": "vo", "file_unique_id": "vo"}}, "голосове"),
                           ("video_note", {"video_note": {"file_id": "vn", "file_unique_id": "vn"}}, "кружечок"),
                           ("document", {"document": {"file_id": "dc", "file_unique_id": "dc"}}, "документ")):
    vv, mid = msg(1, reply_to_message={"message_id": NOTIF, "from": BOTF, "chat": {"id": 1}}, **extra)
    cp = calls(vv, "copyMessage")
    ok("reply " + kind + " -> copyMessage", len(cp) == 1 and cp[0]["chat_id"] == OLIA and cp[0]["message_id"] == mid
       and ev()[2]["type"] == label, str(cp) + str(ev()))

vv, mid = msg(1, text="і ще", reply_to_message={"message_id": ACK, "from": BOTF, "chat": {"id": 1}})
ok("reply на «Пішло» = тій самій людині", [p["chat_id"] for p in calls(vv, "copyMessage")] == [OLIA])
vv, mid2 = msg(1, text="доповнюю", reply_to_message={"message_id": mid, "from": {"id": 1}, "chat": {"id": 1}})
ok("reply на своє відправлене = тій самій людині", [p["chat_id"] for p in calls(vv, "copyMessage")] == [OLIA])

# 2. Після рестарту памʼяті нема: адреса з кнопки napys: чи з єдиного «id N»
bot._fb_map.clear()
vv, _ = msg(1, text="після рестарту", reply_to_message={"message_id": 5, "from": BOTF, "text": "щось без id",
            "reply_markup": {"inline_keyboard": bot.person_rows(NINA)}})
ok("адреса з кнопки napys: під сповіщенням", [p["chat_id"] for p in calls(vv, "copyMessage")] == [NINA])
vv, _ = msg(1, text="по id", reply_to_message={"message_id": 6, "from": BOTF,
            "text": "Повідомлення в боті від Оля, @olia, id 777000:\nпривіт"})
ok("адреса з єдиного id у тексті", [p["chat_id"] for p in calls(vv, "copyMessage")] == [OLIA])

# 3. Reply без адреси нікуди не шле і каже про це
vv, _ = msg(1, text="кому?", reply_to_message={"message_id": 7, "from": BOTF, "text": "Оплата 900 грн у банці, але БЕЗ КОДУ."})
ok("reply на сповіщення без id: не пішло, пояснення", not calls(vv, "copyMessage")
   and any(t.startswith("Не пішло: не бачу, кому") and "/do" in t for t in says(vv)), str(says(vv)))
vv, _ = msg(1, text="кому?", reply_to_message={"message_id": 8, "from": BOTF,
            "text": "Оля, @olia, id 777000\nНіна, без юзернейма, id 777001"})
ok("кілька id: не шле нікому", not calls(vv, "copyMessage") and any("кілька людей" in t for t in says(vv)), str(says(vv)))
vv, _ = msg(1, text="моя нотатка id 777000", reply_to_message={"message_id": 9, "from": {"id": 1}, "text": "своє id 777001"})
ok("reply на своє невідправлене: звичайна обробка, не людині", not calls(vv, "copyMessage")
   and not any(t.startswith("Не пішло") for t in says(vv)))

# 4. Альбом: один copyMessages і одне «Пішло»
bot._fb_map[(1, NOTIF)] = OLIA
ids = []
for i in range(3):
    vv, mid = msg(1, media_group_id="ALB1", photo=[{"file_id": "p%d" % i, "file_unique_id": "p%d" % i}],
                  reply_to_message={"message_id": NOTIF, "from": BOTF, "chat": {"id": 1}}, **({"caption": "три кадри"} if i == 0 else {}))
    ids.append(mid)
    ok("альбом: елемент %d поки нікуди" % (i + 1), not calls(vv, "copyMessage") and not calls(vv, "copyMessages"))
VYKLYKY.clear()
bot.album_flush_all()
cms = calls(VYKLYKY, "copyMessages")
ok("альбом: один copyMessages, id по зростанню", len(cms) == 1 and cms[0]["chat_id"] == OLIA
   and cms[0]["message_ids"] == ids and not calls(VYKLYKY, "copyMessage"), str(cms))
ok("альбом: одне «Пішло»", len([t for t in says(VYKLYKY) if t.startswith("Пішло")]) == 1)
ok("альбом: подія «альбом: фото×3» з підписом", ev()[2]["type"] == "альбом: фото×3" and ev()[2]["text"] == "три кадри", str(ev()))
vv, mid = msg(1, media_group_id="ALB1", photo=[{"file_id": "p9", "file_unique_id": "p9"}])
ok("пізній елемент альбому: тій самій людині", [p["chat_id"] for p in calls(vv, "copyMessage")] == [OLIA])
# лише перший елемент з reply, решта приєднуються
ids = []
vv, mid = msg(1, media_group_id="ALB2", photo=[{"file_id": "q0", "file_unique_id": "q0"}],
              reply_to_message={"message_id": NOTIF, "from": BOTF, "chat": {"id": 1}})
ids.append(mid)
vv, mid = msg(1, media_group_id="ALB2", video={"file_id": "q1", "file_unique_id": "q1"})
ids.append(mid)
VYKLYKY.clear()
bot.album_flush_all()
cms = calls(VYKLYKY, "copyMessages")
ok("альбом: елемент без reply приєднується", len(cms) == 1 and cms[0]["message_ids"] == ids
   and ev()[2]["type"] == "альбом: фото×1, відео×1", str(cms) + str(ev()))
# альбом Іри без reply = матеріали, не людині
vv, _ = msg(2, media_group_id="ALB3", photo=[{"file_id": "r0", "file_unique_id": "r0"}])
ok("альбом Іри без reply: у матеріали (Прийняла)", "Прийняла ♥️" in says(vv, 2) and not bot._alb)

# 5. /do: картка, наступне будь-що йде, режим знімається
vv, mid = msg(1, text="/do 777001")
card = [t for t in says(vv) if t.startswith("Наступне ваше повідомлення піде")]
ok("/do: картка з іменем і /skasuvaty", card and "Ніна, без юзернейма, id 777001" in card[0] and "/skasuvaty" in card[0], str(says(vv)))
vv, mid = msg(1, voice={"file_id": "v1", "file_unique_id": "v1"})
cp = calls(vv, "copyMessage")
ok("/do: голосове без reply пішло Ніні", len(cp) == 1 and cp[0]["chat_id"] == NINA and cp[0]["message_id"] == mid
   and ev()[2]["via"] == "do" and ev()[2]["type"] == "голосове", str(cp) + str(ev()))
ok("/do: режим знято (kv теж)", bot._do.get(1) is None and DB["kv"].get("do:1") == "")
vv, _ = msg(1, text="просто текст адміна")
ok("після режиму: звичайна обробка, людині нічого", not calls(vv, "copyMessage"))

vv, _ = msg(1, text="/do 777001")
vv, _ = msg(1, text="/skasuvaty")
ok("/skasuvaty: «Скасовано»", any(t.startswith("Скасовано: Ніна") for t in says(vv)), str(says(vv)))
vv, _ = msg(1, text="після скасування")
ok("/skasuvaty: наступне нікуди", not calls(vv, "copyMessage"))
vv, _ = msg(1, text="/skasuvaty")
ok("/skasuvaty без режиму", any("не було" in t for t in says(vv)))

vv, _ = msg(1, text="/do 777001")
bot._do[1] = (NINA, time.time() - bot.DO_TTL - 5)
vv, _ = msg(1, text="запізно")
ok("/do: через годину сплив, не шле, каже", not calls(vv, "copyMessage") and any("сплив" in t for t in says(vv)), str(says(vv)))
vv, _ = msg(1, text="знову звичайне")
ok("сплилий режим знято", not calls(vv, "copyMessage") and not any("сплив" in t for t in says(vv)))

bot._do.clear()
DB["kv"]["do:1"] = "777000:%d" % time.time()
vv, _ = msg(1, text="після рестарту в режимі")
ok("/do: режим переживає рестарт (kv)", [p["chat_id"] for p in calls(vv, "copyMessage")] == [OLIA])

vv, _ = msg(1, text="/do 999999")
ok("/do невідомому: відмова, режиму нема", any("невідомий" in t for t in says(vv)) and not bot._do.get(1), str(says(vv)))
vv, _ = msg(1, text="/do")
ok("/do без id: підказка", any("Напишіть так: /do" in t for t in says(vv)))
vv, _ = msg(1, text="/do", reply_to_message={"message_id": 6, "from": BOTF, "text": "Новий у боті: Оля, @olia, id 777000"})
ok("/do reply-ем на сповіщення: картка", any(t.startswith("Наступне") and "id 777000" in t for t in says(vv)))
vv, _ = msg(1, text="Мої матеріали")
ok("кнопка «Мої матеріали» адміна в режимі людині не йде", not calls(vv, "copyMessage") and bot._do.get(1))
msg(1, text="/skasuvaty")

# 6. Людина з /do: звичайний CLIENT_TEXT, нікому нічого
vv, _ = msg(OLIA, text="/do 777001", **{"from": {"id": OLIA, "first_name": "Оля", "username": "olia"}})
ok("людина з /do: CLIENT_TEXT", bot.CLIENT_TEXT in says(vv, OLIA) and not calls(vv, "copyMessage")
   and not calls(vv, "sendMessage", NINA), str(says(vv, OLIA)))
ok("людина з /do: режиму нема", not bot._do.get(OLIA))
vv = cb(OLIA, "napys:777001")
ok("кнопка napys: від людини нічого", not calls(vv, "sendMessage") and not bot._do.get(OLIA))
vv = cb(OLIA, "podar:777001")
ok("кнопка podar: від людини: подарунка нема", not calls(vv, "sendDocument"))

# 7. Кнопки: «Написати» = картка, «🎁 Подарунок» = give_gift раз
vv = cb(1, "napys:777000", mid=4321)
ok("кнопка «Написати»: картка reply-ем на сповіщення", any(p["text"].startswith("Наступне") and p.get("reply_parameters", {}).get("message_id") == 4321
                                                          for p in calls(vv, "sendMessage", 1)) and bot._do.get(1)[0] == OLIA)
msg(1, text="/skasuvaty")
vv = cb(1, "podar:777001")
docs = calls(vv, "sendDocument", NINA)
ok("кнопка «Подарунок»: GIFT_HAND і PDF", bot.GIFT_HAND in says(vv, NINA) and len(docs) == 1 and docs[0]["document"] == "MAGNIT"
   and any(t.startswith("Подарунок (три схеми світла) пішов: Ніна") for t in says(vv)), str(says(vv)))
vv = cb(1, "podar:777001")
ok("подарунок вдруге: не дублює", not calls(vv, "sendDocument") and any(t.startswith("Не пішло: Ніна") for t in says(vv)))
vv, _ = msg(1, text="/podarunok 777001")
ok("/podarunok після кнопки: теж не дублює", not calls(vv, "sendDocument") and any(t.startswith("Не пішло") for t in says(vv)))

# 8. Іра: reply йде людині, /do їй не можна, reply на «Прийняла» = матеріал
bot._fb_map[(2, 5555)] = OLIA
vv, _ = msg(2, text="від Іри", reply_to_message={"message_id": 5555, "from": BOTF})
ok("reply Іри -> людині + «Пішло»", [p["chat_id"] for p in calls(vv, "copyMessage")] == [OLIA]
   and any(t.startswith("Пішло") for t in says(vv, 2)))
vv, _ = msg(2, text="/do 777000")
ok("Іра /do: не режим (матеріали)", not bot._do.get(2) and not any(t.startswith("Наступне") for t in says(vv, 2)))
vv, _ = msg(2, text="ще матеріал", reply_to_message={"message_id": 5556, "from": BOTF, "text": "Прийняла ♥️"})
ok("reply Іри на «Прийняла»: матеріал, не «Не пішло»", "Прийняла ♥️" in says(vv, 2)
   and not any(t.startswith("Не пішло") for t in says(vv, 2)))

# 9. 403: не пішло, позначка blocked
bot._fb_map[(1, 7777)] = 404404
vv, _ = msg(1, text="ти тут?", reply_to_message={"message_id": 7777, "from": BOTF})
ok("403: «Не пішло: … заблокувала бота»", any(t.startswith("Не пішло: Блок") and "заблокувала" in t for t in says(vv)), str(says(vv)))
ok("403: позначка blocked:404404", "blocked:404404" in DB["kv"])

# 10. З ПК: /nadislaty/<секрет>
ok("без секрету 404", app.post("/nadislaty/ne-toi", data={"id": "777000", "text": "x"}).status_code == 404)
VYKLYKY.clear()
r = app.post("/nadislaty/sekret", json={"id": "777000", "dry": "1"})
j = r.get_json()
ok("dry: кому, нічого не шле", r.status_code == 200 and j["ok"] and j["to"] == "Оля, @olia, id 777000"
   and not [m for m, p, _ in VYKLYKY if m.startswith("send") or m.startswith("copy")], str(j))
r = app.post("/nadislaty/sekret", json={"id": "999999", "dry": "1"})
ok("dry невідомому: ok=false", r.get_json()["ok"] is False and "не писала" in r.get_json()["error"])
ok("поганий id: 400", app.post("/nadislaty/sekret", json={"id": "abc", "text": "x"}).status_code == 400)
ok("нема що слати: 400", app.post("/nadislaty/sekret", json={"id": "777000"}).status_code == 400)
VYKLYKY.clear()
r = app.post("/nadislaty/sekret", json={"id": "777000", "text": "Привіт з ПК", "by": "yaro"})
sm = calls(VYKLYKY, "sendMessage", OLIA)
ok("текст з ПК", r.get_json()["ok"] and len(sm) == 1 and sm[0]["text"] == "Привіт з ПК" and "reply_markup" not in sm[0], str(sm))
ok("подія via=pc", ev() == (OLIA, "staff_reply", {"by": "yaro", "via": "pc", "type": "текст", "text": "Привіт з ПК"}), str(ev()))
VYKLYKY.clear()
r = app.post("/nadislaty/sekret", json={"id": "777000", "text": "схема", "file_id": "FID9", "kind": "photo"})
sp = calls(VYKLYKY, "sendPhoto", OLIA)
ok("file_id фото з підписом", r.get_json()["ok"] and len(sp) == 1 and sp[0]["photo"] == "FID9" and sp[0]["caption"] == "схема"
   and not calls(VYKLYKY, "sendMessage", OLIA) and r.get_json()["file_id"] == "BIG", str(r.get_json()))
VYKLYKY.clear()
r = app.post("/nadislaty/sekret", data={"id": "777000", "text": "фото з диска",
                                        "file": (io.BytesIO(b"\xff\xd8jpg"), "kadr.jpg")}, content_type="multipart/form-data")
up = calls(VYKLYKY, "sendPhoto")
ok("upload .jpg = фото з підписом", r.get_json()["ok"] and len(up) == 1 and str(up[0]["chat_id"]) == "777000"
   and up[0]["_files"] == {"photo": "kadr.jpg"} and up[0]["caption"] == "фото з диска", str(r.get_json()) + str(up))
VYKLYKY.clear()
dovgyi = "д" * 1100
r = app.post("/nadislaty/sekret", data={"id": "777000", "text": dovgyi,
                                        "file": (io.BytesIO(b"%PDF"), "plan.pdf")}, content_type="multipart/form-data")
seq = [m for m, p, _ in VYKLYKY if m in ("sendMessage", "sendDocument")]
ok("довгий текст: окремо перед файлом, файл без підпису", r.get_json()["ok"] and seq == ["sendMessage", "sendDocument"]
   and "caption" not in calls(VYKLYKY, "sendDocument")[0], str(seq))
VYKLYKY.clear()
r = app.post("/nadislaty/sekret", json={"id": "404404", "text": "x"})
ok("з ПК 403: ok=false, заблокувала", r.status_code == 502 and "заблокувала" in r.get_json()["error"])

# 11. /events показує що, як, хто
page = app.get("/events/sekret").get_data(as_text=True)
ok("/events: [текст, pc, yaro]", "[текст, pc, yaro] Привіт з ПК" in page and "[голосове, do, 1]" in page, page[-300:])

print("\nПАДІННЯ: " + str(PADINNIA) if PADINNIA else "\nУсе зелене")
sys.exit(1 if PADINNIA else 0)
