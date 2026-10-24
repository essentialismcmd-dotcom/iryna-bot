"""24.10: безкоштовне в «Мої матеріали» і повторний вхід з подарунком на руках без воріт підписки."""
import os
os.environ.setdefault("BOT_TOKEN", "x")
import bot, store

kv = {"shema4_given:5": "1", "preset_given:5:eva": "1", "preset_given:55": "1"}
users = {5: {"got_magnet_at": "t"}, 6: {}}
out = []
store.get_user = lambda uid: users.get(uid)
store.kv_get = lambda k: kv.get(k)
store.kv_prefix = lambda pre: [(k, v) for k, v in kv.items() if k.startswith(pre)]
store.log_event = lambda *a, **k: None
bot.lessons_kb = lambda uid, current=None: None
bot.send = lambda uid, text, kb=None: out.append(("text", uid, text)) or True
bot.api = lambda m, **k: out.append(("doc", k.get("chat_id"), k.get("document"))) or {"ok": True}
bot.magnet_ref = lambda: "MAGNET"
bot.send_preset_files = lambda cid, keys: out.append(("preset", cid, tuple(keys))) or True
bot.give_shema4 = lambda cid, hello=True: out.append(("shema4", cid, hello))

assert bot.free_owned(5) == ["shemy", "shema4", "p:eva"], bot.free_owned(5)
assert bot.free_owned(55) == ["p:kolir1"], bot.free_owned(55)
names = [r[0]["text"] for r in bot.moi_kb(5)["inline_keyboard"]]
assert names == ["Три схеми світла", "Схема 4 · циклорама", "Пресет «Єва»"], names
assert bot.moi_kb(6) is None

out.clear()
assert bot.free_again(5, 5, ["p:eva"])
assert out[0] == ("text", 5, bot.FREE_AGAIN) and ("preset", 5, ("eva",)) in out, out
out.clear()
assert bot.free_again(5, 5, ["shema4"]) and ("shema4", 5, False) in out, out
out.clear()
assert bot.free_again(5, 5, ["shemy"]) and ("doc", 5, "MAGNET") in out, out
out.clear()
assert not bot.free_again(6, 6, ["shemy"]) and not out, "нема подарунка: ворота як було"
assert not bot.free_again(5, 5, ["p:maria"]), "інший пресет: звичайний шлях"
assert not bot.resend_free(6, 6, "shema4")
print("ok  безкоштовне в «Мої матеріали», повтор без воріт")
