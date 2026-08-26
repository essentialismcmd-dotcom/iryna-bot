#!/usr/bin/env python3
"""
Бот лійки Iryna Rul. Webhook, без бази.
Новий користувач падає адміну окремим повідомленням.
Адмін може надіслати боту PDF, і бот поверне file_id для змінної MAGNET_URL.
"""

import os, logging
import requests
from flask import Flask, request

TOKEN       = os.environ["BOT_TOKEN"]
ADMIN_ID    = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_URL = os.getenv("CHANNEL_URL", "").strip()
MAGNET_URL  = os.getenv("MAGNET_URL", "").strip()
SECRET      = os.getenv("WEBHOOK_SECRET", "hook")

API = "https://api.telegram.org/bot" + TOKEN
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

HELLO = (
    "Привіт, це Ірина Руль ❤️\n\n"
    "Тут можна забрати мою добірку «Три схеми світла з одного сетапу»: "
    "три різні картинки за одну зйомку, без додаткового обладнання.\n\n"
    "Тисніть кнопку нижче, і я одразу надішлю файл."
)
AFTER = (
    "Готово, файл вище ❤️\n\n"
    "Копіюйте розстановку, віддайте схемам 5 хвилин на студії і подивіться, що вийде.\n\n"
    "У каналі «Iryna Rul | для своїх» я розбираю світло, ретуш і бекстейджі без води."
)
AFTER_NO_CHANNEL = (
    "Готово, файл вище ❤️\n\n"
    "Копіюйте розстановку, віддайте схемам 5 хвилин на студії і подивіться, що вийде.\n\n"
    "Напишіть, як спробуєте, мені цікаво, що вийшло."
)


def api(method, **params):
    try:
        r = requests.post(API + "/" + method, json=params, timeout=25)
        j = r.json()
        if not j.get("ok"):
            log.warning("%s: %s", method, j.get("description"))
        return j.get("result")
    except Exception as e:
        log.warning("%s: %s", method, e)
        return None


def send(chat_id, text, markup=None):
    return api("sendMessage", chat_id=chat_id, text=text,
               reply_markup=markup, disable_web_page_preview=True)


def magnet_kb():
    return {"inline_keyboard": [[{"text": "Забрати три схеми світла", "callback_data": "magnet"}]]}


def channel_kb():
    if not CHANNEL_URL:
        return None
    return {"inline_keyboard": [[{"text": "Канал «для своїх»", "url": CHANNEL_URL}]]}


def notify_admin(u, source):
    if not ADMIN_ID:
        return
    uname = u.get("username")
    who = "@" + uname if uname else "id " + str(u.get("id"))
    name = " ".join([x for x in [u.get("first_name"), u.get("last_name")] if x]) or "без імені"
    send(ADMIN_ID, "Новий у боті: " + name + ", " + who + "\nМітка: " + (source or "без мітки"))


def give_magnet(chat_id):
    if not MAGNET_URL:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірі в дірект ❤️")
        return
    api("sendDocument", chat_id=chat_id, document=MAGNET_URL)
    send(chat_id, AFTER if CHANNEL_URL else AFTER_NO_CHANNEL, channel_kb())


@app.post("/" + SECRET)
def hook():
    upd = request.get_json(silent=True) or {}
    try:
        if "message" in upd:
            m = upd["message"]
            chat_id = m["chat"]["id"]
            u = m.get("from", {})
            doc = m.get("document")
            if doc and u.get("id") == ADMIN_ID:
                send(chat_id, "file_id цього файлу:\n" + doc.get("file_id", "?"))
                return "ok"
            text = (m.get("text") or "").strip()
            if text.startswith("/start"):
                parts = text.split(None, 1)
                notify_admin(u, parts[1].strip() if len(parts) > 1 else "")
                send(chat_id, HELLO, magnet_kb())
            else:
                send(chat_id, "Щоб забрати добірку, тисніть кнопку нижче ❤️", magnet_kb())
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            api("answerCallbackQuery", callback_query_id=cq["id"])
            if cq.get("data") == "magnet":
                give_magnet(cq["message"]["chat"]["id"])
    except Exception as e:
        log.exception("update failed: %s", e)
    return "ok"


@app.get("/")
def health():
    return "ok"


@app.get("/setup")
def setup():
    base = request.url_root.rstrip("/")
    r = api("setWebhook", url=base + "/" + SECRET,
            allowed_updates=["message", "callback_query"])
    return "setWebhook: " + str(r)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
