#!/usr/bin/env python3
"""/zakrip: адмін публікує закріп у канал з кнопкою в бот. Без мережі і бази."""
import os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.update({"BOT_TOKEN": "test:token", "WEBHOOK_SECRET": "sekret", "ADMIN_ID": "1",
                   "NO_THREADS": "1", "TEST_MODE": "1"})
for k in ("DATABASE_URL", "ZAKRIP_CHAT", "ZAKRIP_URL", "ZAKRIP_BTN"):
    os.environ.pop(k, None)

import requests

VYKLYKY = []
FAIL = {}   # метод -> опис помилки


class _R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


def fake_post(url, json=None, data=None, files=None, timeout=None):
    method = url.rsplit("/", 1)[-1]
    VYKLYKY.append((method, json or data or {}))
    if method in FAIL:
        return _R({"ok": False, "error_code": 400, "description": FAIL[method]})
    return _R({"ok": True, "result": {"message_id": 4242} if method != "pinChatMessage" else True})


requests.post = fake_post
sys.modules.pop("bot", None)
import bot

app = bot.app.test_client()
PADINNIA = []


def perevirka(nazva, umova, dovidka=""):
    print(("  ok  " if umova else "  ПАДІННЯ  ") + nazva + (": " + dovidka if dovidka else ""))
    if not umova:
        PADINNIA.append(nazva)


def msg(text, uid=1, **extra):
    m = {"message_id": 10, "chat": {"id": uid}, "from": {"id": uid, "first_name": "Y"}, "text": text}
    m.update(extra)
    return app.post("/sekret", json={"message": m})


def vyklyky(method):
    return [p for m, p in VYKLYKY if m == method]


def adminu():
    return [p.get("text", "") for p in vyklyky("sendMessage") if p.get("chat_id") == 1]


KB = {"inline_keyboard": [[{"text": "Хочу на майстер-клас",
                            "url": "https://t.me/iryna_rul_bot?start=mk"}]]}

perevirka("типовий канал чернетка", bot.ZAKRIP_CHAT == "-1004303013438", bot.ZAKRIP_CHAT)

# 1. /zakrip текст: пост у канал з кнопкою, закріп, відповідь адміну
VYKLYKY.clear()
txt = "/zakrip Привіт, я Іра ♥️\nТут мої зйомки"
msg(txt, entities=[{"type": "bot_command", "offset": 0, "length": 7},
                   {"type": "bold", "offset": 8, "length": 6}])
post = [p for p in vyklyky("sendMessage") if p.get("chat_id") == "-1004303013438"]
perevirka("пост пішов у канал", len(post) == 1, str(post))
perevirka("текст без команди", post and post[0]["text"] == "Привіт, я Іра ♥️\nТут мої зйомки")
perevirka("кнопка URL у бот", post and post[0]["reply_markup"] == KB, str(post and post[0].get("reply_markup")))
perevirka("форматування зсунуте", post and post[0].get("entities") == [{"type": "bold", "offset": 0, "length": 6}],
          str(post and post[0].get("entities")))
pin = vyklyky("pinChatMessage")
perevirka("закріплено той самий пост", pin == [{"chat_id": "-1004303013438", "message_id": 4242,
                                               "disable_notification": True}], str(pin))
perevirka("адмін: Готово, id", any(t.startswith("Готово, id 4242") for t in adminu()), str(adminu()))

# 2. reply /zakrip: копія повідомлення з кнопкою
VYKLYKY.clear()
msg("/zakrip", reply_to_message={"message_id": 7, "chat": {"id": 1}, "text": "Текст закріпу"})
cp = vyklyky("copyMessage")
perevirka("reply копіює повідомлення", cp == [{"chat_id": "-1004303013438", "from_chat_id": 1,
                                              "message_id": 7, "reply_markup": KB}], str(cp))
perevirka("reply: закріп і Готово", len(vyklyky("pinChatMessage")) == 1
          and any(t.startswith("Готово, id") for t in adminu()))

# 3. порожній /zakrip: підказка, нічого в канал
VYKLYKY.clear()
msg("/zakrip")
perevirka("порожній: нічого в канал", not vyklyky("copyMessage") and not vyklyky("pinChatMessage")
          and all(p.get("chat_id") == 1 for p in vyklyky("sendMessage")))
perevirka("порожній: підказка", any("/zakrip" in t for t in adminu()), str(adminu()))

# 4. бот не адмін каналу: зрозуміла помилка
VYKLYKY.clear()
FAIL["sendMessage"] = "Bad Request: need administrator rights in the channel chat"
bot.ZAKRIP_CHAT  # той самий
msg("/zakrip Текст")
FAIL.clear()
perevirka("не адмін: без закріпу", not vyklyky("pinChatMessage"))
perevirka("не адмін: зрозуміла помилка", any("Бот не адмін каналу" in t for t in adminu()), str(adminu()))

# 5. пост є, закріп не вдався
VYKLYKY.clear()
FAIL["pinChatMessage"] = "Bad Request: not enough rights to manage pinned messages in the chat"
msg("/zakrip Текст")
FAIL.clear()
perevirka("закріп не вдався: каже про id і права",
          any("не закріплено" in t and "4242" in t and "Бот не адмін" in t for t in adminu()), str(adminu()))

# 6. не адмін: команда не працює
VYKLYKY.clear()
msg("/zakrip Чужий текст", uid=777)
perevirka("чужий /zakrip не публікує", not any(p.get("chat_id") == "-1004303013438"
                                               for p in vyklyky("sendMessage")) and not vyklyky("pinChatMessage"))

# 7. колір кнопки (Bot API 9.4, style): слово першим після /zakrip, у текстовому режимі і в reply
bot.ZAKRIP_BTN = "Хочу на МК ♥️"
for slovo, stil, tekst_knopky in (("зелена", "success", "Хочу на МК ♥️"),
                                  ("синя", "primary", "Хочу на МК ♥️"),
                                  ("червона", "danger", "Хочу на МК 🤍")):
    VYKLYKY.clear()
    txt = "/zakrip " + slovo + " Тест кнопки: " + slovo
    cut = len("/zakrip " + slovo + " ")
    msg(txt, entities=[{"type": "bot_command", "offset": 0, "length": 7},
                       {"type": "bold", "offset": cut, "length": 4}])
    post = [p for p in vyklyky("sendMessage") if p.get("chat_id") == "-1004303013438"]
    perevirka(slovo + ": текст без команди і слова кольору",
              len(post) == 1 and post[0]["text"] == "Тест кнопки: " + slovo, str(post))
    perevirka(slovo + ": entities зсунуті", post and post[0].get("entities") == [
        {"type": "bold", "offset": 0, "length": 4}], str(post and post[0].get("entities")))
    perevirka(slovo + ": style " + stil + " і текст кнопки",
              post and post[0]["reply_markup"] == {"inline_keyboard": [[
                  {"text": tekst_knopky, "url": "https://t.me/iryna_rul_bot?start=mk", "style": stil}]]},
              str(post and post[0].get("reply_markup")))
    perevirka(slovo + ": закріп", len(vyklyky("pinChatMessage")) == 1)
    VYKLYKY.clear()
    msg("/zakrip " + slovo, reply_to_message={"message_id": 7, "chat": {"id": 1}, "text": "Текст"})
    cp = vyklyky("copyMessage")
    perevirka(slovo + ": reply копіює з кнопкою style",
              len(cp) == 1 and cp[0]["reply_markup"]["inline_keyboard"][0][0].get("style") == stil
              and cp[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == tekst_knopky, str(cp))

# без слова кольору: кнопка без style, серце як є
VYKLYKY.clear()
msg("/zakrip Привіт, червона шапочка")
post = [p for p in vyklyky("sendMessage") if p.get("chat_id") == "-1004303013438"]
perevirka("слово кольору не першим: текст цілий, без style",
          post and post[0]["text"] == "Привіт, червона шапочка"
          and post[0]["reply_markup"]["inline_keyboard"][0][0] == {
              "text": "Хочу на МК ♥️", "url": "https://t.me/iryna_rul_bot?start=mk"},
          str(post))

# ZAKRIP_STYLE для бойового режиму: без слова бере змінну, слово перебиває
bot.ZAKRIP_STYLE = "success"
VYKLYKY.clear()
msg("/zakrip Звичайний закріп")
post = [p for p in vyklyky("sendMessage") if p.get("chat_id") == "-1004303013438"]
perevirka("ZAKRIP_STYLE=success: кнопка зелена", post
          and post[0]["reply_markup"]["inline_keyboard"][0][0].get("style") == "success", str(post))
VYKLYKY.clear()
msg("/zakrip синя Інший")
post = [p for p in vyklyky("sendMessage") if p.get("chat_id") == "-1004303013438"]
perevirka("слово кольору перебиває ZAKRIP_STYLE", post
          and post[0]["reply_markup"]["inline_keyboard"][0][0].get("style") == "primary", str(post))
bot.ZAKRIP_STYLE = ""
bot.ZAKRIP_BTN = "Хочу на майстер-клас"

# слово кольору саме по собі без reply: підказка, нічого в канал
VYKLYKY.clear()
msg("/zakrip червона")
perevirka("колір без тексту і без reply: нічого в канал", not vyklyky("copyMessage")
          and not vyklyky("pinChatMessage")
          and not [p for p in vyklyky("sendMessage") if p.get("chat_id") == "-1004303013438"])

print()
if PADINNIA:
    print("ПАДІНЬ:", len(PADINNIA), PADINNIA)
    sys.exit(1)
print("усе зелене")
