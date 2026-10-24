"""24.10: Д2 після пресета і схеми 4 (раніше лише після трьох схем)."""
import os
os.environ.setdefault("BOT_TOKEN", "x")
from datetime import datetime, timezone
import bot, store

sent, kv = [], {"shema4_given:2": "1"}
store.touch_candidates = lambda *a, **k: [(1, "t"), (2, None), (3, None)] if k.get("with_gift") else []
store.kv_get = lambda k: kv.get(k)
store.kv_claim = lambda k: kv.setdefault(k, "c") == "c"
store.kv_set = lambda k, v: kv.__setitem__(k, v)
store.log_event = lambda *a, **k: None
store.user_texts = lambda uid: ""
bot.owned_keys = lambda uid, real=False: []
bot.send = lambda uid, text, kb=None: sent.append((uid, text)) or True
bot.GIFT_FOR_SUB = True
bot.touch_run(datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc))      # 12:00 Київ
t = dict(sent)
assert t[1].startswith("Три схеми у вас"), t
assert t[2].startswith("Схема з циклорамою"), t
assert t[3] == bot.TOUCH_D2_PRESET, t
assert "%" not in t[2] and "%" not in t[3]
print("ok  Д2: схеми, схема 4, пресет")
