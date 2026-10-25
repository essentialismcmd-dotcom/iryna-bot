"""24.10, аудит 2: назва пресета у воротах, «Є питання до Іри» на картці курсу, Д-курс через добу."""
import os, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("PAY_URL", "https://pay.test/x")
import bot, store
bot.send_card_file = lambda chat_id, path, text, markup=None: bot.send(chat_id, text, markup)   # 25.10: картка курсу з фото, тексти перевіряємо як раніше
from datetime import datetime, timezone

kv = {}
out = []
store.kv_get = lambda k, d=None: kv.get(k, d)
store.kv_set = lambda k, v: kv.__setitem__(k, v)
store.kv_claim = lambda k: (k not in kv) and (kv.__setitem__(k, "1") or True)
store.log_event = lambda *a, **k: None
store.add_purchase = lambda *a, **k: None
bot.send = lambda uid, text, kb=None: out.append((uid, text, kb)) or True
bot.notify = lambda *a, **k: None
bot.lead_once = lambda *a, **k: False

# ворота пресета: назва з реклами
assert "«Єва»" in bot.preset_hello_sub(["eva"]) and "Колір 1" not in bot.preset_hello_sub(["eva"])
assert bot.preset_hello_sub(["kolir1"]) == bot.PRESET_HELLO_SUB

# картка курсу: кнопка питання другою, після оплати
bot.cold = lambda uid: False
bot.pick_product(7, 7, {"id": 7}, "k12z", gate=False)
uid, text, kb = out[-1]
rows = [r[0].get("callback_data") or r[0].get("url", "")[:5] for r in kb["inline_keyboard"]]
assert kb["inline_keyboard"][1][0].get("url") == bot.IRA_DM_URL, rows
assert str(bot.PRODUCTS["k12z"]["uah"]) in text, text
assert "dorogo" not in str(kb) and kv.get("kurs_pershyi:7"), kb

# питання відкрите 24 год, потім ні
assert bot.ask_open(7) is None
bot.ask_set(7, "kurs")
assert bot.ask_open(7) == "kurs"
kv["ask:7"] = "mk:%d" % (time.time() - 25 * 3600)
assert bot.ask_open(7) is None

# Д-курс: один раз, лише строк особистої ціни і кнопка курсу
kv["kurs_pershyi:9"] = str(int(time.time()) - 24 * 3600)
out.clear()
store.kurs_pending = lambda lo, hi, skip, pre: [9]
store.touch_candidates = lambda *a, **k: []
bot.owned_keys = lambda uid, real=False: []
bot._touch_ok = lambda uid: True
now = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)     # 12:00 Київ
bot.touch_run(now)
bot.touch_run(now)
assert len(out) == 1 and str(bot._K12Z) in out[0][1] and str(bot._K12) in out[0][1], out
cb = [r[0]["callback_data"] for r in out[0][2]["inline_keyboard"]]
assert cb == ["kurs:pay"], cb
assert "%" not in bot.KURS_DOROGO % bot._G
print("ok  аудит 2: пресет з назвою, питання до Іри, Д-курс")
