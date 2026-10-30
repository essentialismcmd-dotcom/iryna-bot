#!/usr/bin/env python3
"""30.10, слово Yaro: курс без ціни, людину ведемо в особисті; ціна другою кнопкою, після розмови і з кабінету одразу."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1", "NO_THREADS": "1",
                   "COURSES_ON": "1", "COURSE_BUNDLE_ONLY": "1", "COURSE_PRICES": "3200,1900,3300",
                   "PAY_URL": "https://pay.test/jar", "NOTIFY_IDS": "1"})
os.environ.pop("DATABASE_URL", None)
from datetime import datetime, timezone
import bot, store
KV, SENT, ALBUM, BUY, EV = {}, [], [], [], []
store.kv_get = lambda k, default=None: KV.get(k, default)
store.kv_set = lambda k, v: KV.__setitem__(k, v)
store.add_purchase = lambda *a, **k: BUY.append(a)
store.log_event = lambda uid, kind, payload=None: EV.append(kind)
bot.lead_once = lambda uid, what: True
bot.notify = lambda *a, **k: None
bot.send_kurs_album = lambda chat_id: ALBUM.append(chat_id)
bot.send_card_file = lambda chat_id, path, text, markup=None: SENT.append((text, markup))
bot.send = lambda chat_id, text, markup=None, **k: SENT.append((text, markup)) or True
bad = []
def ok(name, cond, extra=""):
    print(("  ok  " if cond else "  ПАДІННЯ  ") + name + (": " + str(extra) if extra and not cond else ""))
    if not cond: bad.append(name)
U = {"id": 5, "first_name": "A"}
bot.pick_product(5, 5, U, "k12", gate=False)
t, kb = SENT[-1]
rows = kb["inline_keyboard"]
ok("вітрина без ціни", "грн" not in t and "3300" not in t and "2970" not in t, t)
ok("влазить у підпис картки", len(t) <= 1024, len(t))
ok("перша кнопка в особисті з готовим текстом", rows[0][0]["text"] == "Спитати Іру" and "iryna_rul_studio?text=" in rows[0][0]["url"], rows)
ok("друга кнопка ціна", rows[1][0] == {"text": "Ціна і оплата", "callback_data": "kurs:tsina"}, rows)
ok("вікно 48 год не почалось", not KV.get("kurs_pershyi:5"))
ok("покупки нема, подія є", not BUY and "kurs_vitryna" in EV)
ok("альбом один", len(ALBUM) == 1)
bot.pick_product(5, 5, U, "k12", gate=False)
ok("вітрина вдруге: альбом не повторюється", len(ALBUM) == 1)
bot.pick_product(5, 5, U, "k12", gate=False, oplata=True)
t, kb = SENT[-1]
ok("тиск на ціну: ціна і оплата", "3300 грн" in t and "2970 грн до " in t and any("pay.test" in (r[0].get("url") or "") for r in kb["inline_keyboard"]), t)
ok("тиск на ціну: вікно пішло, покупка є, альбом не повторився", KV.get("kurs_pershyi:5") and BUY and len(ALBUM) == 1)
KV["rozmova:6"] = "1"
bot.pick_product(6, 6, {"id": 6}, "k12", gate=False)
ok("після розмови одразу ціна", "грн" in SENT[-1][0], SENT[-1][0])
KV["tsina:7"] = "2500"
bot.pick_product(7, 7, {"id": 7}, "k12", gate=False)
ok("своя ціна одразу картка", "2500 грн" in SENT[-1][0], SENT[-1][0])
# дотик через 20-36 год тим, хто бачив лише вітрину
store.kurs_pending = lambda lo, hi, skip, pre: []
store.kurs_vitryna_pending = lambda lo, hi, skip, pre: [8]
store.touch_candidates = lambda *a, **k: []
store.kv_claim = lambda k: True
bot.owned_keys = lambda uid, real=False: []
bot._touch_ok = lambda uid: True
SENT.clear()
bot.touch_run(datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc))
ok("дотик тому, хто бачив лише вітрину", any("Бачила, ви відкривали курс" in s[0] for s in SENT), SENT)
print("ПАДІНЬ:", len(bad)); sys.exit(1 if bad else 0)
