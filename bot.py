#!/usr/bin/env python3
"""
Бот лійки Iryna Rul. Webhook, без бази.
Магніт віддається автоматично. Повний гайд у трьох пакетах,
видача в один тап адміном після оплати.
Адмін може надіслати боту файл, і бот поверне file_id.
"""

import os, time, logging, threading
import requests
from flask import Flask, request

TOKEN         = os.environ["BOT_TOKEN"]
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_URL   = os.getenv("CHANNEL_URL", "").strip()
MAGNET_URL    = os.getenv("MAGNET_URL", "").strip()
GUIDE_FILE_ID = os.getenv("GUIDE_FILE_ID", "").strip()
PAY_URL       = os.getenv("PAY_URL", "").strip()
SECRET        = os.getenv("WEBHOOK_SECRET", "hook")
BASE_URL      = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")


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
GUIDE_INTRO = (
    "Повний гайд «Світло» ❤️\n\n"
    "Це всі мої робочі схеми: від чистої комерції до кольорової градації світла. "
    "Кожна з 3D-розстановкою з двох ракурсів, налаштуваннями і кадрами з реальних зйомок.\n\n"
    "Три варіанти, оберіть свій."
)

TIERS = {
    "t1": {
        "name": "Гайд «Світло»",
        "price": 15,
        "btn": "Гайд, 15 $",
        "text": (
            "Гайд «Світло», 15 $\n\n"
            "Повний файл з усіма схемами, розстановками і налаштуваннями. "
            "Доступ залишається назавжди."
        ),
        "extra": "",
    },
    "t2": {
        "name": "Гайд + розбір одного кадру",
        "price": 21,
        "btn": "Гайд + розбір кадру, 21 $",
        "text": (
            "Гайд «Світло» + розбір одного кадру, 21 $\n\n"
            "Той самий гайд, плюс ви надсилаєте мені один свій знімок, "
            "і я особисто розбираю, що там зі світлом і що змінити, щоб стало краще."
        ),
        "extra": "Після оплати надішліть кадр прямо сюди, я подивлюсь і відповім.",
    },
    "t3": {
        "name": "Гайд + розбір трьох кадрів",
        "price": 39,
        "btn": "Гайд + розбір трьох кадрів, 39 $",
        "text": (
            "Гайд «Світло» + розбір трьох кадрів, 39 $\n\n"
            "Гайд, розбір трьох ваших знімків і мої відповіді на питання по вашому обладнанню: "
            "що у вас є і як з цим зібрати мої схеми."
        ),
        "extra": "Після оплати надішліть три кадри прямо сюди, я подивлюсь і відповім.",
    },
}


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


def tiers_kb():
    return {"inline_keyboard": [[{"text": TIERS[k]["btn"], "callback_data": k}] for k in ("t1", "t2", "t3")]}


def pay_kb():
    if PAY_URL:
        return {"inline_keyboard": [[{"text": "Оплатити", "url": PAY_URL}]]}
    return None


def give_kb(uid, tier):
    return {"inline_keyboard": [[{"text": "Видати гайд", "callback_data": "give:" + str(uid) + ":" + tier}]]}


def who(u):
    uname = u.get("username")
    tag = "@" + uname if uname else "без юзернейма"
    name = " ".join([x for x in [u.get("first_name"), u.get("last_name")] if x]) or "без імені"
    return name + ", " + tag + ", id " + str(u.get("id"))


def notify(text, markup=None):
    for cid in NOTIFY_IDS:
        send(cid, text, markup)


def give_magnet(chat_id):
    if not MAGNET_URL:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ❤️")
        return
    r = api("sendDocument", chat_id=chat_id, document=MAGNET_URL)
    if not r:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ❤️")
        return
    send(chat_id, AFTER, after_kb())


def give_guide(uid, tier):
    if not GUIDE_FILE_ID:
        send(uid, "Хвилинку, зараз надішлю файл ❤️")
        return False
    r = api("sendDocument", chat_id=uid, document=GUIDE_FILE_ID)
    if not r:
        return False
    tail = "Гайд ваш назавжди ❤️"
    extra = TIERS.get(tier, {}).get("extra", "")
    if extra:
        tail += "\n\n" + extra
    send(uid, tail)
    return True


@app.post("/" + SECRET)
def hook():
    upd = request.get_json(silent=True) or {}
    try:
        if "message" in upd:
            m = upd["message"]
            chat_id = m["chat"]["id"]
            u = m.get("from", {})
            doc = m.get("document")
            if doc and u.get("id") in NOTIFY_IDS:
                send(chat_id, "file_id цього файлу:\n" + doc.get("file_id", "?"))
                return "ok"
            text = (m.get("text") or "").strip()
            if text.startswith("/start"):
                parts = text.split(None, 1)
                src = parts[1].strip() if len(parts) > 1 else ""
                notify("Новий у боті: " + who(u) + "\nМітка: " + (src or "без мітки"))
                send(chat_id, HELLO, magnet_kb())
            elif u.get("id") not in NOTIFY_IDS:
                notify("Повідомлення в боті від " + who(u) + ":\n" + (text or "[не текст]"))
                send(chat_id, "Прийняла, зараз подивлюсь і відповім ❤️")
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            api("answerCallbackQuery", callback_query_id=cq["id"])
            data = cq.get("data") or ""
            chat_id = cq["message"]["chat"]["id"]
            u = cq.get("from", {})
            if data == "magnet":
                give_magnet(chat_id)
            elif data == "guide":
                send(chat_id, GUIDE_INTRO, tiers_kb())
            elif data in TIERS:
                t = TIERS[data]
                body = t["text"]
                if PAY_URL:
                    body += "\n\nНатисніть «Оплатити», а після оплати надішліть сюди скрін. Я одразу відкрию доступ."
                else:
                    body += "\n\nНапишу вам зараз особисто і скину реквізити для оплати."
                send(chat_id, body, pay_kb())
                notify("ЗАЯВКА: " + t["name"] + ", " + str(t["price"]) + " $\n" + who(u),
                       give_kb(u.get("id"), data))
            elif data.startswith("give:") and u.get("id") in NOTIFY_IDS:
                _, uid, tier = (data.split(":") + ["", ""])[:3]
                ok = give_guide(int(uid), tier)
                send(chat_id, "Видано ✅" if ok else "Не вдалося надіслати, перевір GUIDE_FILE_ID")
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


def keepalive():
    while True:
        time.sleep(600)
        try:
            requests.get(BASE_URL + "/", timeout=15)
        except Exception:
            pass


if BASE_URL:
    threading.Thread(target=keepalive, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
