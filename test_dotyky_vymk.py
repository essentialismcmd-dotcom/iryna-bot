"""30.10: Д2 і W1 вимкнено за замовчуванням; Д1 і дотик про курс лишаються."""
import os
os.environ.setdefault("BOT_TOKEN", "x")
os.environ.pop("TOUCH_D2_ON", None)
os.environ.pop("TOUCH_W1_ON", None)
from datetime import datetime, timezone
import bot, store

calls = []
store.touch_candidates = lambda *a, **k: calls.append(a[1]) or []
store.kurs_pending = lambda *a, **k: calls.append("kurs") or []
store.kurs_vitryna_pending = lambda *a, **k: calls.append("vitryna") or []
bot.GIFT_FOR_SUB = True
assert not bot.TOUCH_D2_ON and not bot.TOUCH_W1_ON
bot.touch_run(datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc))      # 11:00 Київ
assert bot.TOUCH_D1[0] in calls and "kurs" in calls and "vitryna" in calls, calls
assert bot.TOUCH_D2[0] not in calls and bot.TOUCH_W1[0] not in calls, calls
print("ok  Д2 і W1 мовчать, Д1 і курс працюють")
