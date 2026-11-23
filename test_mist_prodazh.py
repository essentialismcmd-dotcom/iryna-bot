#!/usr/bin/env python3
"""23.11: ручна оплата без Yaro. POST /mist/<key>/prodazh і /mist/<key>/vydaty під MIST_KEY (ті самі функції,
що /prodazh/<SECRET> і /vydaty/<SECRET>); /prodazh, /vydaty, /zakrip у боті від Іри (IRA_ID) і адміна поза NOTIFY_IDS.
Без мережі й бази: підставні store.* у пам'яті.

Запуск:  python test_mist_prodazh.py   (виходить 0, якщо все зелене)
"""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
# NOTIFY_IDS навмисно без адміна (1) і без Іри (2): права мають іти з ADMIN_ID / IRA_ID
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "IRA_ID": "2",
                   "NOTIFY_IDS": "5", "NO_THREADS": "1", "MIST_KEY": "kliuch", "GUIDE_FILE_ID": "GUIDE"})
for k in ("DATABASE_URL", "IRA_ON", "TEST_MODE", "KABINET_URL", "KABINET_KEY"):
    os.environ.pop(k, None)

import requests
VYKLYKY = []


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None, headers=None):
    VYKLYKY.append((url.rsplit("/", 1)[-1], json or data or {}))
    return _R({"ok": True, "result": {"message_id": len(VYKLYKY)}})


requests.post = fake_post
import time; time.sleep = lambda *_: None
import bot, store

# ---------- підставна база ----------
PUR, KV, EV = {}, {}, []


def ensure_purchase(uid, product, tier=None, order_code=None, amount_uah=None, **k):
    PUR.setdefault(order_code, {"user_id": uid, "product": product, "tier": tier, "order_code": order_code,
                                "amount_uah": amount_uah, "status": "new"})


def mark_paid(code, uah=None):
    p = PUR.get(code)
    if p and p["status"] == "new":
        p["status"] = "paid"
        if uah is not None:
            p["amount_uah"] = uah


def mark_delivered(code):
    if code in PUR:
        PUR[code]["status"] = "delivered"


store.get_purchase = lambda code: PUR.get(code)
store.ensure_purchase = ensure_purchase
store.mark_paid = mark_paid
store.mark_delivered = mark_delivered
store.kv_set = lambda k, v: KV.__setitem__(k, v)
store.kv_get = lambda k: KV.get(k)
store.log_event = lambda uid, kind, payload=None: EV.append((uid, kind, payload))

app = bot.app.test_client()
bad = []


def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond:
        bad.append(name)


def kod(uid, key):
    return bot.order_code(uid, key)


print("1. /mist/<key>/prodazh")
r = app.post("/mist/zlyi/prodazh", json={"id": 801, "uah": 2400, "key": "k12", "by": "test"})
ok("чужий ключ 404, як у сусідів, нічого не пише", r.status_code == 404 and not PUR and not KV and not EV, r.status_code)

r = app.post("/mist/kliuch/prodazh", json={"id": 801, "uah": 2400, "key": "k12", "by": "pomichnyk"})
j = r.get_json() or {}
p = PUR.get(kod(801, "k12")) or {}
ok("правильний ключ 200, ok і код k12", r.status_code == 200 and j.get("ok") is True and j.get("code") == kod(801, "k12"), j)
ok("рядка не було: створено paid→delivered з сумою", p.get("status") == "delivered" and p.get("amount_uah") == 2400
   and p.get("tier") == "k12" and p.get("product") == bot.PRODUCTS["k12"]["product"], p)
ok("kv prodazh:<код> = сума", KV.get("prodazh:" + kod(801, "k12")) == "2400", KV)
ok("події prodazh і prodazh_pc з by", (801, "prodazh", {"code": kod(801, "k12"), "uah": 2400, "tier": "k12"}) in EV
   and (801, "prodazh_pc", {"by": "pomichnyk"}) in EV, EV)
ok("текст для персоналу", str(j.get("text", "")).startswith("Зараховано: ") and "2400 грн" in j.get("text", ""), j)

r = app.post("/mist/kliuch/prodazh", data={"id": "802", "uah": "299", "key": "gaid", "by": "f"})
j = r.get_json() or {}
ok("форма і key=gaid → гайд t1", r.status_code == 200 and j.get("code") == kod(802, "t1")
   and (PUR.get(kod(802, "t1")) or {}).get("status") == "delivered", j)

r = app.post("/mist/kliuch/prodazh", json={"id": 803, "uah": 2970, "key": "k12z", "by": "f"})
ok("key=k12z лишається k12z", (r.get_json() or {}).get("code") == kod(803, "k12z"), r.get_json())

PUR[kod(804, "k12")] = {"user_id": 804, "order_code": kod(804, "k12"), "status": "paid", "amount_uah": 555}
app.post("/mist/kliuch/prodazh", json={"id": 804, "uah": 2400, "by": "f"})
ok("рядок уже був: не чіпаємо, лише kv", PUR[kod(804, "k12")]["amount_uah"] == 555
   and PUR[kod(804, "k12")]["status"] == "paid" and KV.get("prodazh:" + kod(804, "k12")) == "2400", PUR[kod(804, "k12")])

n0 = (len(PUR), len(KV), len(EV))
for body in ({"id": "x", "uah": 100}, {"id": 805, "uah": "сто"}, {"id": 805}, {"uah": 100}, {"id": -5, "uah": 100}):
    r = app.post("/mist/kliuch/prodazh", json=body)
    ok("нечислові/порожні поля 400: " + str(body), r.status_code == 400 and (r.get_json() or {}).get("ok") is False, r.status_code)
ok("після 400 нічого не записано", (len(PUR), len(KV), len(EV)) == n0)

r1 = app.post("/prodazh/sekret", json={"id": 806, "uah": 100, "by": "a"}).get_json()
r2 = app.post("/mist/kliuch/prodazh", json={"id": 807, "uah": 100, "by": "a"}).get_json()
ok("відповідь того ж вигляду, що /prodazh/<SECRET>", sorted(r1) == sorted(r2) == ["code", "ok", "text"], (r1, r2))

print("2. /mist/<key>/vydaty")
DEL, ISS = [], []
bot.deliver = lambda uid, key: DEL.append((uid, key)) or True
bot._pay_issue = lambda uid, key, code, kop, extra="": (ISS.append((uid, key, code, kop, extra)),
                                                        ensure_purchase(uid, "course", tier=key, order_code=code),
                                                        mark_paid(code), mark_delivered(code))
r = app.post("/mist/zlyi/vydaty", json={"id": 901, "uah": 2400, "key": "k12z"})
ok("чужий ключ 404, нічого не видано", r.status_code == 404 and not DEL and not ISS)
r = app.post("/mist/kliuch/vydaty", json={"id": "x", "uah": 1})
ok("погані поля 400", r.status_code == 400 and not ISS)
r = app.post("/mist/kliuch/vydaty", json={"id": 901, "uah": 2400, "key": "k12z", "by": "pomichnyk"})
j = r.get_json() or {}
ok("видача тим самим _pay_issue: ok, delivered", j.get("ok") is True and j.get("status") == "delivered"
   and ISS and ISS[-1][:4] == (901, "k12z", kod(901, "k12z"), 240000) and "pomichnyk" in ISS[-1][4], (j, ISS))
r = app.post("/mist/kliuch/vydaty", json={"id": 902, "uah": 0, "key": "t1", "by": "f"})
ok("uah 0 = подарунок без рядка покупки", (r.get_json() or {}).get("podarunok") == "t1" and (902, "t1") in DEL
   and kod(902, "t1") not in PUR, r.get_json())

print("3. Команди в боті від Іри (2) і адміна (1) поза NOTIFY_IDS")


def msg(uid, text):
    VYKLYKY.clear()
    return app.post("/sekret", json={"update_id": 1, "message": {"message_id": 9, "date": int(time.time()),
                    "chat": {"id": uid, "type": "private"}, "from": {"id": uid, "first_name": "Т"}, "text": text}})


def vidpovid(uid):
    return [str(p.get("text", "")) for m, p in VYKLYKY if m == "sendMessage" and p.get("chat_id") == uid]


msg(2, "/prodazh 811 2400")
ok("Іра: /prodazh зараховує", (PUR.get(kod(811, "k12")) or {}).get("status") == "delivered"
   and KV.get("prodazh:" + kod(811, "k12")) == "2400" and any(t.startswith("Зараховано: ") for t in vidpovid(2)), vidpovid(2))
msg(2, "/prodazh 812 299 gaid")
ok("Іра: /prodazh … gaid → t1", KV.get("prodazh:" + kod(812, "t1")) == "299")
msg(2, "/prodazh 812")
ok("Іра: без суми підказка, нічого не пише", any(t.startswith("Напишіть так: /prodazh") for t in vidpovid(2)))
msg(1, "/prodazh 813 2400")
ok("адмін поза NOTIFY_IDS: /prodazh зараховує", KV.get("prodazh:" + kod(813, "k12")) == "2400")
msg(5, "/prodazh 814 2400")
ok("NOTIFY_IDS як і раніше", KV.get("prodazh:" + kod(814, "k12")) == "2400")
msg(777, "/prodazh 815 2400")
ok("стороння людина: нічого не зараховано", "prodazh:" + kod(815, "k12") not in KV and kod(815, "k12") not in PUR)

GM = []
bot.give_manual = lambda by, target, key: GM.append((by, target, key)) or True
msg(2, "/vydaty 821 gaid")
ok("Іра: /vydaty видає", GM == [(2, 821, "t1")], GM)
msg(777, "/vydaty 822")
ok("стороння людина: /vydaty ні", len(GM) == 1, GM)

ZK = []
bot.zakrip = lambda m: ZK.append(m["from"]["id"]) or "закріплено"
msg(2, "/zakrip текст")
msg(1, "/zakrip текст")
msg(5, "/zakrip текст")
msg(777, "/zakrip текст")
ok("/zakrip: Іра й адмін так, NOTIFY_IDS і сторонні ні (як і було)", ZK == [2, 1], ZK)

print()
print("ПАДІНЬ:", len(bad))
for x in bad:
    print("  -", x)
sys.exit(1 if bad else 0)
