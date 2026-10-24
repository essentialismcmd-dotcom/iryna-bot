"""24.10: Т1 через 5+ днів: схема 4, якщо її нема, інакше пресет; хто має все, нічого не отримує."""
import os
os.environ.setdefault("BOT_TOKEN", "x")
from datetime import datetime, timezone
import bot, store

sent, kv, got = [], {"shema4_given:2": "1", "shema4_given:3": "1", "preset_given:3": "1", "touch_w1:4": "1"}, []
store.touch_candidates = lambda *a, **k: [(1, "t"), (2, "t"), (3, "t"), (4, "t")] if a[1] == bot.TOUCH_W1[0] else []
store.kv_get = lambda k: kv.get(k)
store.kv_claim = lambda k: k not in kv and not kv.__setitem__(k, "c")
store.kv_set = lambda k, v: kv.__setitem__(k, v)
store.log_event = lambda *a, **k: None
store.user_texts = lambda uid: ""
bot.owned_keys = lambda uid, real=False: []
bot.send = lambda uid, text, kb=None: sent.append((uid, text)) or True
bot.give_shema4 = lambda uid: got.append((uid, "shema4"))
bot.give_preset = lambda uid, keys=None: got.append((uid, "preset"))
bot.GIFT_FOR_SUB = True
bot.touch_run(datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc))      # 12:00 Київ
assert sorted(got) == [(1, "shema4"), (2, "preset")], got
assert sorted(u for u, _ in sent) == [1, 2], sent
assert all(t == bot.TOUCH_W1_LEAD for _, t in sent)
bot.touch_run(datetime(2026, 10, 25, 9, 10, tzinfo=timezone.utc))
assert len(got) == 2, got
print("ok  Т1: схема 4, пресет, повтору нема")
