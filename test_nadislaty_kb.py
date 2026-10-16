#!/usr/bin/env python3
"""
/nadislaty з кнопками (15.10) БЕЗ мережі і бази. Розсилка 15.10: Коля і Флозік отримують текст G2 з кнопками
«Відкрити урок» + канал, Оксана і Julia лише запрошення в канал з кнопкою. kb=kanal | urok_kanal додає кнопки
push1 (канал веде на інвайт push1 з PUSH1_URL, урок на урок 1.5 у кабінеті); mark=push1 ставить людині push1
(kv push1:<id>, події) і вдруге не шле; dry показує кнопки з посиланнями і нічого не шле; без kb усе як було.
Запуск: python -B test_nadislaty_kb.py
"""
import os, sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

INVITE = "https://t.me/+TESTinvite"
os.environ.update({"BOT_TOKEN": "555:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "NO_THREADS": "1",
                   "MAGNET_URL": "MAGNIT", "NOTIFY_IDS": "1", "IRA_ID": "2", "CHANNEL_URL": "https://t.me/test_kanal",
                   "PUSH1_URL": INVITE, "KABINET_URL": "https://kab.test", "KABINET_KEY": "k", "GUIDE_PRICE": "199"})
for _k in ("DATABASE_URL", "LEAD_IDS", "PUSH_SKIP_IDS", "PUSH1_G1", "PUSH1_G2", "PUSH1_KNOPKA", "PUSH1_UROK"):
    os.environ.pop(_k, None)

import requests
VYKLYKY = []
ZBII = {404404}


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    method = url.rsplit("/", 1)[-1]
    p = dict(json or data or {})
    mid = 1000 + len(VYKLYKY)
    VYKLYKY.append((method, p, mid))
    cid = p.get("chat_id")
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        pass
    if cid in ZBII:
        return _R({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
    if method == "getChat":
        return _R({"ok": True, "result": {"id": cid, "type": "private", "first_name": "Чат" + str(cid)}})
    return _R({"ok": True, "result": {"message_id": mid}})


requests.post = fake_post
import bot
import store

DB = {"kv": {}, "events": [], "users": {}}
PUSHED = []


def kv_set(k, v):
    DB["kv"][k] = str(v)


def log_event(uid, kind, payload=None):
    DB["events"].append((uid, kind, payload))


store.ON = True
store.q = lambda *a, **k: None
store.kv_get = lambda k, default=None: DB["kv"].get(k, default)
store.kv_set = kv_set
store.log_event = log_event
store.get_user = lambda uid: DB["users"].get(uid)
bot.kabinet_mist.push_user = lambda uid: PUSHED.append(uid)
bot.bg = lambda fn, *a, **k: fn(*a, **k)
bot.time.sleep = lambda s: None

app = bot.app.test_client()
PADINNIA = []
KOLIA, OKSANA, BLOK = 485297554, 646573380, 404404
for u, n in ((KOLIA, "Коля"), (OKSANA, "Оксана"), (BLOK, "Блок")):
    DB["users"][u] = {"user_id": u, "first_name": n, "username": None}


def ok(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


def sends(chat=None):
    return [p for m, p, _ in VYKLYKY if m.startswith("send") and (chat is None or p.get("chat_id") == chat)]


def post(**kw):
    return app.post("/nadislaty/sekret", json=kw)


G2 = "Привіт, я Іра♥️ Дарую вам свій урок ретуші."
INV = "Привіт, я Іра♥️ Запрошую вас у свій тг канал."

# 1. dry показує кнопки і нічого не шле
VYKLYKY.clear()
r = post(id=str(KOLIA), dry="1", kb="urok_kanal", mark="push1")
j = r.get_json()
ok("dry urok_kanal: 2 кнопки, урок web_app у кабінеті, канал = інвайт push1",
   r.status_code == 200 and j["ok"] and j["dry"] and [b["text"] for b in j["kb"]] == ["Відкрити урок", "Канал «для своїх»"]
   and j["kb"][0] == {"text": "Відкрити урок", "url": "https://kab.test/?p=1.5", "web_app": True}
   and j["kb"][1] == {"text": "Канал «для своїх»", "url": INVITE, "web_app": False}, str(j))
ok("dry нічого не шле", not sends())
j = post(id=str(OKSANA), dry="1", kb="kanal").get_json()
ok("dry kanal: одна кнопка каналу", j["ok"] and j["kb"] == [{"text": "Канал «для своїх»", "url": INVITE, "web_app": False}], str(j))
j = post(id=str(KOLIA), dry="1").get_json()
ok("dry без kb: як було (без kb у відповіді)", j["ok"] and "kb" not in j and j["to"].startswith("Коля"), str(j))

# 2. погані параметри
ok("kb невідомий: 400", post(id=str(KOLIA), text="x", kb="zzz").status_code == 400)
ok("kb з файлом: 400", post(id=str(KOLIA), text="x", kb="kanal", file_id="F", kind="photo").status_code == 400)
ok("mark без kb: 400", post(id=str(KOLIA), text="x", mark="push1").status_code == 400)
ok("mark не push1: 400", post(id=str(KOLIA), text="x", kb="kanal", mark="inshe").status_code == 400)
ok("kb без тексту: 400, нічого не шле", post(id=str(KOLIA), kb="kanal").status_code == 400 and not sends())
ok("поганих викликів не було", not sends())

# 3. без kb усе як було: ні кнопок, ні позначок
VYKLYKY.clear()
j = post(id=str(KOLIA), text="звичайне", by="yaro").get_json()
sm = sends(KOLIA)
ok("без kb: без reply_markup і без push1", j["ok"] and len(sm) == 1 and "reply_markup" not in sm[0]
   and "push1:" + str(KOLIA) not in DB["kv"], str(sm))

# 4. G2: Коля, текст + урок + канал, позначка push1, події, людина в кабінеті
VYKLYKY.clear()
r = post(id=str(KOLIA), text=G2, kb="urok_kanal", mark="push1", by="arkhitektor")
j = r.get_json()
sm = sends(KOLIA)
rm = (sm[0].get("reply_markup") or {}).get("inline_keyboard") if sm else None
ok("G2 пішло одним повідомленням з текстом дослівно", r.status_code == 200 and j["ok"] and len(sm) == 1
   and sm[0]["text"] == G2, str(j))
ok("G2 кнопки: урок web_app + канал в одному ряду", rm == [[{"text": "Відкрити урок", "web_app": {"url": "https://kab.test/?p=1.5"}},
                                                           {"text": "Канал «для своїх»", "url": INVITE}]], str(rm))
ok("G2: людина в кабінеті до кнопки", PUSHED == [KOLIA], str(PUSHED))
ok("G2: kv push1 = ok G2", DB["kv"].get("push1:" + str(KOLIA)) == "ok G2", str(DB["kv"]))
kinds = [e[1] for e in DB["events"] if e[0] == KOLIA]
ok("G2: події staff_reply, lesson_gift, push1", kinds[-3:] == ["staff_reply", "lesson_gift", "push1"], str(kinds))
ok("G2: подія push1 з seg", [e[2] for e in DB["events"] if e[0] == KOLIA and e[1] == "push1"][-1]
   == {"seg": "G2", "ok": True, "via": "pc"})

# 5. вдруге mark=push1 не шле ні dry-ok, ні реально
VYKLYKY.clear()
r = post(id=str(KOLIA), text=G2, kb="urok_kanal", mark="push1")
ok("вдруге: 409 і нічого не пішло", r.status_code == 409 and not r.get_json()["ok"] and not sends(), str(r.get_json()))
j = post(id=str(KOLIA), dry="1", kb="urok_kanal", mark="push1").get_json()
ok("dry вдруге: ok=false, причина", j["ok"] is False and "вже був" in j["error"], str(j))

# 6. запрошення: Оксана, текст + канал, без уроку, без lesson_gift
VYKLYKY.clear()
PUSHED.clear()
r = post(id=str(OKSANA), text=INV, kb="kanal", mark="push1")
sm = sends(OKSANA)
rm = (sm[0].get("reply_markup") or {}).get("inline_keyboard") if sm else None
ok("запрошення пішло: текст + одна кнопка каналу", r.get_json()["ok"] and len(sm) == 1 and sm[0]["text"] == INV
   and rm == [[{"text": "Канал «для своїх»", "url": INVITE}]], str(sm))
ok("запрошення: без файлу, без кабінету", not [m for m, p, _ in VYKLYKY if m in ("sendDocument", "sendPhoto")] and not PUSHED)
ok("запрошення: kv push1 = ok INV, без lesson_gift", DB["kv"].get("push1:" + str(OKSANA)) == "ok INV"
   and not [e for e in DB["events"] if e[0] == OKSANA and e[1] == "lesson_gift"], str(DB["kv"]))

# 7. 403: не позначено, помилка, можна повторити пізніше
VYKLYKY.clear()
r = post(id=str(BLOK), text=INV, kb="kanal", mark="push1")
ok("403: 502, заблокувала, push1 не позначено", r.status_code == 502 and "заблокувала" in r.get_json()["error"]
   and "push1:" + str(BLOK) not in DB["kv"], str(r.get_json()))

# 8. після mark /push1 go її не бачить як кандидата: рядок з kv push1 дає причину «push1 уже був»
rows = [{"user_id": KOLIA, "role": "client", "tiers": ["t1"], "got_magnet_at": datetime(2026, 9, 27, tzinfo=timezone.utc),
         "ev_magnet": True, "ev_lesson": False, "kab_lesson": False, "last_seen_at": datetime(2026, 9, 27, tzinfo=timezone.utc),
         "last_event": datetime(2026, 9, 27, tzinfo=timezone.utc), "texts": "", "blocked_at": None,
         "push1": DB["kv"]["push1:" + str(KOLIA)], "username": None, "first_name": "Коля", "last_name": None}]
store.push_rows = lambda: rows
sg = bot.push1_segments(datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc))
ok("push1_segments: Коля після mark у «push1 уже був», у G2 її нема", not sg["seg"]["G2"]
   and [p["id"] for p in sg["skip"]["push1 уже був"]] == [KOLIA], str(sg))


# 9. 16.10: kb=hajd кнопка гайда (callback guide), mark=hajd199 окремий kv-ключ, вдруге 409; push1 не чіпає
VYKLYKY.clear()
j = post(id=str(KOLIA), dry="1", kb="hajd", mark="hajd199").get_json()
ok("dry hajd: ok попри push1 у kv, кнопка гайда без url", j["ok"] and j["kb"] == [{"text": "Гайд, 199 грн", "url": None, "web_app": False}], str(j))
HJ = "Сім років світла в одному гайді."
r = post(id=str(KOLIA), text=HJ, kb="hajd", mark="hajd199", by="arkhitektor")
sm = sends(KOLIA)
rm = (sm[0].get("reply_markup") or {}).get("inline_keyboard") if sm else None
ok("hajd пішло: текст + кнопка «Гайд, 199 грн» з callback guide", r.status_code == 200 and len(sm) == 1 and sm[0]["text"] == HJ
   and rm == [[{"text": "Гайд, 199 грн", "callback_data": "guide"}]], str(r.get_json()) + str(rm))
ok("hajd: kv hajd199 = ok hajd, push1 як був", DB["kv"].get("hajd199:" + str(KOLIA)) == "ok hajd"
   and DB["kv"].get("push1:" + str(KOLIA)) == "ok G2", str(DB["kv"]))
ok("hajd: подія hajd199", [e for e in DB["events"] if e[0] == KOLIA and e[1] == "hajd199"], str(DB["events"][-2:]))
VYKLYKY.clear()
r = post(id=str(KOLIA), text=HJ, kb="hajd", mark="hajd199")
ok("hajd вдруге: 409, нічого не пішло", r.status_code == 409 and "hajd199" in r.get_json()["error"] and not sends(), str(r.get_json()))
ok("mark невідомий: 400", post(id=str(KOLIA), text="x", kb="hajd", mark="inshe").status_code == 400)
print("\nПАДІННЯ: " + str(PADINNIA) if PADINNIA else "\nУсе зелене")
sys.exit(1 if PADINNIA else 0)
