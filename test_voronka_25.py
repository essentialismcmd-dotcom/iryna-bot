#!/usr/bin/env python3
"""Аудит воронки 25.10: вступ у канал повз «Я підписалась» дає подарунок, слово «пресет» у чаті бота веде до пресета,
«Preset» з великої літери і нові мітки ManyChat ідуть своїм шляхом, збій подарунка не бреше «файл вище». БЕЗ мережі і бази."""
import os, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "NO_THREADS": "1",
                   "TEST_MODE": "1", "COURSES_ON": "1", "COURSE_BUNDLE_ONLY": "1", "NOTIFY_IDS": "1",
                   "CHANNEL_URL": "https://t.me/iryna_rul_photographer", "MAGNET_URL": "https://files.test/magnit.pdf"})
os.environ.pop("DATABASE_URL", None)
import requests
CALLS = []
class _R:
    def __init__(self, j): self._j = j
    def json(self): return self._j
def fake_post(url, json=None, data=None, files=None, timeout=None, headers=None):
    CALLS.append((url.rsplit("/", 1)[-1], json or data or {}))
    return _R({"ok": True, "result": {"message_id": 1}})
requests.post = fake_post
time.sleep = lambda *_: None
import bot

bad = 0
def check(name, cond):
    global bad
    print(("ok   " if cond else "FAIL ") + name)
    bad += not cond

KV, USERS, SUBS, SENT = {}, {}, [], []
bot.store.kv_get = lambda k, default=None: KV.get(k, default)
bot.store.kv_set = lambda k, v: KV.__setitem__(k, str(v))
bot.store.kv_del = lambda k: KV.pop(k, None)
bot.store.kv_prefix = lambda p: [(k, v) for k, v in KV.items() if k.startswith(p)]
bot.store.kv_claim = lambda k: False if k in KV else (KV.__setitem__(k, "1") or True)
bot.store.log_event = lambda *a, **k: None
bot.store.get_user = lambda uid: USERS.get(uid)
bot.store.touch_user = lambda u, **k: {"is_new": True}
bot.bg = lambda fn, *a, **k: None
bot.send_card = lambda chat_id, pic, text, kb=None, **k: SENT.append((chat_id, text, kb))
bot.sub_check = lambda chat_id, uid, u: SUBS.append(uid)
CH = bot.CHANNEL_ID

def vstup(uid, old="left", new="member", chat=None):
    return {"chat_member": {"chat": chat or {"id": -100, "username": CH.lstrip("@")},
                            "from": {"id": uid}, "old_chat_member": {"status": old, "user": {"id": uid}},
                            "new_chat_member": {"status": new, "user": {"id": uid, "first_name": "Т"}}}}
post = lambda upd: bot.app.test_client().post("/sekret", json=upd)

# 1. вступ у канал: стартувала бота, подарунка нема → sub_check сам
USERS[501] = {"user_id": 501}
post(vstup(501))
check("вступ без кнопки: подарунок сам", SUBS == [501])
# 2. не стартувала бота: нічого
SUBS.clear(); post(vstup(502))
check("не стартувала бота: тиша", SUBS == [])
# 3. уже має схеми і нічого не чекає: нічого
SUBS.clear(); USERS[503] = {"user_id": 503, "got_magnet_at": "x"}; post(vstup(503))
check("схеми вже має: тиша", SUBS == [])
# 4. має схеми, але чекає пресет: пресет
SUBS.clear(); USERS[504] = {"user_id": 504, "got_magnet_at": "x"}; KV["preset_wait:504"] = "1"; post(vstup(504))
check("має схеми, чекає пресет: видаємо", SUBS == [504])
# 5. чужий чат і вихід з каналу не рахуються
SUBS.clear(); post(vstup(501, chat={"id": -999, "username": "inshyi"})); post(vstup(501, old="member", new="left"))
check("чужий чат і вихід: тиша", SUBS == [])
check("allowed_updates з chat_member", "chat_member" in open(bot.__file__, encoding="utf-8").read().split("def setup")[1][:300])

# 6. слово «пресет» у чаті: ворота пресета, а не «напишіть в інстаграм»
bot.kanal_member_fresh = lambda uid: (False, "ні")
SENT.clear(); USERS[601] = {"user_id": 601}
post({"message": {"message_id": 1, "chat": {"id": 601, "type": "private"}, "from": {"id": 601, "first_name": "Н"}, "text": "Пресет"}})
check("слово «Пресет»: ворота пресета", KV.get("preset_wait:601") and SENT and "пресет" in SENT[-1][1].lower() and "sub:check" in str(SENT[-1][2]))

# 7. «/start Preset» і нова мітка ManyChat: свої шляхи
SENT.clear()
post({"message": {"message_id": 1, "chat": {"id": 602, "type": "private"}, "from": {"id": 602, "first_name": "Н"}, "text": "/start Preset"}})
check("/start Preset: шлях пресета", KV.get("preset_wait:602") is not None)
SENT.clear()
post({"message": {"message_id": 1, "chat": {"id": 603, "type": "private"}, "from": {"id": 603, "first_name": "Н"}, "text": "/start shema2_mc"}})
check("/start shema2_mc: привіт схем з «Я підписалась»", SENT and SENT[-1][1] == bot.SVITLO_HELLO and "sub:check" in str(SENT[-1][2]))
# 8. уже в каналі, прийшла по схеми: одразу sub_check
bot.kanal_member_fresh = lambda uid: (True, "так")
SUBS.clear()
post({"message": {"message_id": 1, "chat": {"id": 604, "type": "private"}, "from": {"id": 604, "first_name": "Н"}, "text": "/start svitlo"}})
check("уже в каналі: без воріт", SUBS == [604])

# 9. збій подарунка: позначку знято, людині чесно
bot.magnet_ref = lambda: None
CALLS.clear(); USERS[701] = {"user_id": 701}
bot.give_gift(701, "текст")
check("збій подарунка: gift: знято", "gift:701" not in KV)
check("збій подарунка: людині «тимчасово недоступний»", any("тимчасово недоступний" in str(p.get("text")) for m, p in CALLS if int(p.get("chat_id") or 0) == 701))
sys.exit(1 if bad else 0)
