#!/usr/bin/env python3
"""
Бот лійки Iryna Rul. Webhook, без бази.
Магніт віддається автоматично.
Повний гайд у трьох пакетах, оплата в банку Monobank,
бот сам бачить платіж за кодом у коментарі і віддає файл.
TEST_MODE=1 вмикає імітацію оплати для чорнових прогонів.
"""

import os, re, time, logging, threading
import requests
from flask import Flask, request

TOKEN         = os.environ["BOT_TOKEN"]
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_URL   = os.getenv("CHANNEL_URL", "").strip()
MAGNET_URL    = os.getenv("MAGNET_URL", "").strip()
GUIDE_FILE_ID = os.getenv("GUIDE_FILE_ID", "").strip()
PAY_URL       = os.getenv("PAY_URL", "").strip()
MONO_TOKEN    = os.getenv("MONO_TOKEN", "").strip()
MONO_JAR      = os.getenv("MONO_JAR", "").strip()
TEST_MODE     = os.getenv("TEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
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
MONO = "https://api.monobank.ua"
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
        "uah": 650,
        "btn": "Гайд, 650 грн",
        "text": (
            "Гайд «Світло», 650 грн\n\n"
            "Повний файл з усіма схемами, розстановками і налаштуваннями. "
            "Доступ залишається назавжди."
        ),
        "extra": "",
    },
    "t2": {
        "name": "Гайд + розбір одного кадру",
        "uah": 900,
        "btn": "Гайд + розбір кадру, 900 грн",
        "text": (
            "Гайд «Світло» + розбір одного кадру, 900 грн\n\n"
            "Той самий гайд, плюс ви надсилаєте мені один свій знімок, "
            "і я особисто розбираю, що там зі світлом і що змінити, щоб стало краще."
        ),
        "extra": "Надішліть кадр прямо сюди, я подивлюсь і відповім.",
    },
    "t3": {
        "name": "Гайд + розбір трьох кадрів",
        "uah": 1650,
        "btn": "Гайд + розбір трьох кадрів, 1650 грн",
        "text": (
            "Гайд «Світло» + розбір трьох кадрів, 1650 грн\n\n"
            "Гайд, розбір трьох ваших знімків і мої відповіді по вашому обладнанню: "
            "що у вас є і як з цим зібрати мої схеми."
        ),
        "extra": "Надішліть три кадри прямо сюди, я подивлюсь і відповім.",
    },
}

TEST_CARD = "0000 0000 0000 0000"

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def b36(n):
    n = int(n)
    if n == 0:
        return "0"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = DIGITS[r] + s
    return s


def unb36(s):
    n = 0
    for ch in s:
        n = n * 36 + DIGITS.index(ch)
    return n


def order_code(uid, tier):
    return "IR" + b36(uid) + "-" + tier[-1]


CODE_RE = re.compile(r"IR([0-9A-Z]+)-([123])", re.I)


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


def pay_kb(tier):
    rows = []
    if PAY_URL:
        rows.append([{"text": "Перейти до оплати", "url": PAY_URL}])
    if TEST_MODE:
        rows.append([{"text": "Я оплатив (тест)", "callback_data": "paid:" + tier}])
    return {"inline_keyboard": rows} if rows else None


def give_kb(uid, tier):
    return {"inline_keyboard": [[{"text": "Видати гайд вручну", "callback_data": "give:" + str(uid) + ":" + tier}]]}


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
    tail = "Оплату бачу, гайд ваш назавжди ❤️"
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
                code = order_code(u.get("id"), data)
                body = t["text"]
                if PAY_URL:
                    body += ("\n\nТисніть кнопку і у коментарі до платежу впишіть код:\n"
                             + code +
                             "\n\nЗа цим кодом я вас упізнаю, і файл прийде сюди сам, "
                             "зазвичай за хвилину після оплати.")
                elif TEST_MODE:
                    body += ("\n\nЧОРНОВИК, реквізити ще не підключені.\n"
                             "Картка: " + TEST_CARD + ", отримувач Ірина Р.\n"
                             "Код у коментарі до платежу: " + code +
                             "\n\nНатисніть «Я оплатив (тест)», щоб пройти крок оплати.")
                else:
                    body += "\n\nНапишу вам зараз особисто і скину реквізити."
                send(chat_id, body, pay_kb(data))
                notify("ЗАЯВКА: " + t["name"] + ", " + str(t["uah"]) + " грн\n"
                       + who(u) + "\nКод: " + code, give_kb(u.get("id"), data))
            elif data.startswith("paid:") and TEST_MODE:
                tier = data.split(":")[1]
                ok = give_guide(u.get("id"), tier)
                if not ok:
                    send(chat_id, "Тест: файл ще не підключений, впиши GUIDE_FILE_ID.")
                notify("ТЕСТ оплати: " + TIERS.get(tier, {}).get("name", tier) + "\n" + who(u))
            elif data.startswith("give:") and u.get("id") in NOTIFY_IDS:
                parts = (data.split(":") + ["", ""])[:3]
                ok = give_guide(int(parts[1]), parts[2])
                send(chat_id, "Видано" if ok else "Не вдалося, перевір GUIDE_FILE_ID")
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


@app.get("/jars/" + SECRET)
def jars():
    if not MONO_TOKEN:
        return "MONO_TOKEN не заданий"
    try:
        r = requests.get(MONO + "/personal/client-info",
                         headers={"X-Token": MONO_TOKEN}, timeout=20)
        if r.status_code != 200:
            return "Monobank: " + str(r.status_code) + " " + r.text
        out = []
        for j in r.json().get("jars", []):
            out.append(j.get("title", "?") + "  ->  " + j.get("id", "?"))
        return "<pre>" + ("\n".join(out) or "банок не знайдено") + "</pre>"
    except Exception as e:
        return "помилка: " + str(e)


def handle_tx(tx):
    amount = tx.get("amount", 0)
    comment = (tx.get("comment") or "") + " " + (tx.get("description") or "")
    m = CODE_RE.search(comment.replace(" ", ""))
    if not m:
        notify("Оплата " + str(amount // 100) + " грн у банці, але без коду.\n"
               "Коментар: " + (tx.get("comment") or "порожній") + "\n"
               "Видай гайд вручну з відповідної заявки.")
        return
    try:
        uid = unb36(m.group(1).upper())
    except Exception:
        return
    tier = "t" + m.group(2)
    need = TIERS.get(tier, {}).get("uah", 0) * 100
    if amount < need * 0.9:
        notify("Оплата " + str(amount // 100) + " грн за кодом " + m.group(0)
               + ", а треба " + str(need // 100) + " грн. Гайд не видано.")
        return
    ok = give_guide(uid, tier)
    notify(("Оплата " + str(amount // 100) + " грн, код " + m.group(0)
            + ". Гайд видано автоматично.") if ok
           else ("Оплата " + str(amount // 100) + " грн, код " + m.group(0)
                 + ", але файл не пішов. Перевір GUIDE_FILE_ID."))


def mono_poll():
    seen = set()
    primed = False
    while True:
        time.sleep(70)
        if not (MONO_TOKEN and MONO_JAR):
            continue
        try:
            frm = int(time.time()) - 3600
            r = requests.get(MONO + "/personal/statement/" + MONO_JAR + "/" + str(frm),
                             headers={"X-Token": MONO_TOKEN}, timeout=25)
            if r.status_code != 200:
                continue
            txs = r.json()
            if not isinstance(txs, list):
                continue
            for tx in txs:
                tid = tx.get("id")
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                if tx.get("amount", 0) <= 0:
                    continue
                if not primed:
                    continue
                handle_tx(tx)
            primed = True
            if len(seen) > 5000:
                seen = set(list(seen)[-2000:])
        except Exception as e:
            log.warning("mono: %s", e)


def keepalive():
    while True:
        time.sleep(600)
        try:
            requests.get(BASE_URL + "/", timeout=15)
        except Exception:
            pass


if BASE_URL:
    threading.Thread(target=keepalive, daemon=True).start()
threading.Thread(target=mono_poll, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
