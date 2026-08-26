#!/usr/bin/env python3
"""
Бот лійки Iryna Rul. Webhook, без бази.
Новий користувач і заявка на повний гайд падають адміну окремим повідомленням.
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


def _ids(raw):
    out = []
    for part in raw.replace(" ", "").split(","):
        try:
            out.append(int(part))
        except ValueError:
            pass
    return out


NOTIFY_IDS = _ids(os.getenv("NOTIFY_IDS", "")) or ([ADMIN_ID] if ADMIN_ID else [])

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
    "У каналі «Iryna Rul | для своїх» я розбираю світло, ретуш і бекстейджі без води. "
    "А якщо хочете всі мої схеми, а не три, тисніть другу кнопку."
)
GUIDE = (
    "Класно ❤️\n\n"
    "У повному гайді «Світло» зібрані всі мої робочі схеми: від чистої комерції "
    "до кольорової градації світла. Кожна з 3D-розстановкою з двох ракурсів, "
    "налаштуваннями і кадрами з реальних зйомок.\n\n"
    "Зараз напишу вам особисто і розкажу деталі."
)


def api(method, **params):
    params = {k: v for k, v in params.items() if v is not None}
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


def after_kb():
    rows = []
    if CHANNEL_URL:
        rows.append([{"text": "Канал «для своїх»", "url": CHANNEL_URL}])
    rows.append([{"text": "Хочу повний гайд «Світло»", "callback_data": "guide"}])
    return {"inline_keyboard": rows}


def who(u):
    uname = u.get("username")
    tag = "@" + uname if uname else "без юзернейма"
    name = " ".join([x for x in [u.get("first_name"), u.get("last_name")] if x]) or "без імені"
    return name + ", " + tag + ", id " + str(u.get("id"))


def notify(text):
    for cid in NOTIFY_IDS:
        send(cid, text)


def give_magnet(chat_id):
    if not MAGNET_URL:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ❤️")
        return
    r = api("sendDocument", chat_id=chat_id, document=MAGNET_URL)
    if not r:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ❤️")
        return
    send(chat_id, AFTER, after_kb())


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
                src = parts[1].strip() if len(parts) > 1 else ""
                notify("Новий у боті: " + who(u) + "\nМітка: " + (src or "без мітки"))
                send(chat_id, HELLO, magnet_kb())
            else:
                send(chat_id, "Щоб забрати добірку, тисніть кнопку нижче ❤️", magnet_kb())
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            api("answerCallbackQuery", callback_query_id=cq["id"])
            data = cq.get("data")
            chat_id = cq["message"]["chat"]["id"]
            if data == "magnet":
                give_magnet(chat_id)
            elif data == "guide":
                notify("ЗАЯВКА НА ПОВНИЙ ГАЙД\n" + who(cq.get("from", {})))
                send(chat_id, GUIDE)
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
