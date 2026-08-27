#!/usr/bin/env python3
"""
Бот лійки Iryna Rul.
Лійка: магніт, три пакети гайду, оплата в банку Monobank.
Задачник: /todo, стан живе у закріпленому повідомленні чату.
"""

import os, re, time, logging, threading
import requests
from flask import Flask, request

import store

TOKEN         = os.environ["BOT_TOKEN"]
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))
IRA_ID        = int(os.getenv("IRA_ID", "0"))
CHANNEL_URL   = os.getenv("CHANNEL_URL", "").strip()
MAGNET_URL    = os.getenv("MAGNET_URL", "").strip()
GUIDE_FILE_ID = os.getenv("GUIDE_FILE_ID", "").strip()
PAY_URL       = os.getenv("PAY_URL", "").strip()
MONO_TOKEN    = os.getenv("MONO_TOKEN", "").strip()
MONO_JAR      = os.getenv("MONO_JAR", "").strip()
TEST_MODE     = os.getenv("TEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
TASKS_ON      = os.getenv("TASKS_ON", "").strip().lower() in ("1", "true", "yes", "on")
IRA_ON        = os.getenv("IRA_ON", "").strip().lower() in ("1", "true", "yes", "on")
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
TEAM = {}
if ADMIN_ID:
    TEAM[ADMIN_ID] = "Яро"
if IRA_ID:
    TEAM[IRA_ID] = "Іра"

def team_on(uid):
    return TASKS_ON if uid == ADMIN_ID else IRA_ON


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
    "t1": {"name": "Гайд «Світло»", "uah": 650, "btn": "Гайд, 650 грн",
           "text": ("Гайд «Світло», 650 грн\n\n"
                    "Повний файл з усіма схемами, розстановками і налаштуваннями. "
                    "Доступ залишається назавжди."),
           "extra": ""},
    "t2": {"name": "Гайд + розбір одного кадру", "uah": 900, "btn": "Гайд + розбір кадру, 900 грн",
           "text": ("Гайд «Світло» + розбір одного кадру, 900 грн\n\n"
                    "Той самий гайд, плюс ви надсилаєте мені один свій знімок, "
                    "і я особисто розбираю, що там зі світлом і що змінити, щоб стало краще."),
           "extra": "Надішліть кадр прямо сюди, я подивлюсь і відповім."},
    "t3": {"name": "Гайд + розбір трьох кадрів", "uah": 1650, "btn": "Гайд + розбір трьох кадрів, 1650 грн",
           "text": ("Гайд «Світло» + розбір трьох кадрів, 1650 грн\n\n"
                    "Гайд, розбір трьох ваших знімків і мої відповіді по вашому обладнанню: "
                    "що у вас є і як з цим зібрати мої схеми."),
           "extra": "Надішліть три кадри прямо сюди, я подивлюсь і відповім."},
}

TEST_CARD = "0000 0000 0000 0000"
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

SEED = {
    "Іра": [
        "Надіслати правки до магніту і до чорновика гайду",
        "Вільні дати на вересень і слоти на два тижні вперед",
        "Валюта: долари чи євро, обрати одну",
        "Дві-три перевірені студії з назвою, районом і ціною",
        "Що робимо, якщо клієнт переносить дату або просить повернення",
        "Прочитати файл «Як продавати» і сказати, з чим не згодна",
        "Пара кадрів до і після ретуші плюс три речення, що там зроблено",
        "Чи можна показувати кадри зі зйомки для sixzeros у каналі",
        "Скинути в бот фото і беки зі зйомок для постів у каналі",
    ],
    "Яро": [
        "Закрити клієнтку на 2 вересня: передоплата 2000 грн",
        "Клієнтка на 6 вересня: перерахувати майстрів або з'їсти 100 доларів",
        "Підключити банку Monobank і токен у Render",
        "Вимкнути тестовий режим у боті перед реальним трафіком",
        "Поставити мітки в посиланнях бота: svitlo, retush, kanal",
        "Прибити плейсменти в Meta, щоб не зливало у Facebook",
    ],
}


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
TASK_RE = re.compile(r"^([✅▫️⬜▶️\s]*)#(\d+)\s+(.*?)(?:\s+←.*)?$")


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
    if not api("sendDocument", chat_id=uid, document=GUIDE_FILE_ID):
        return False
    tail = "Оплату бачу, гайд ваш назавжди ❤️"
    extra = TIERS.get(tier, {}).get("extra", "")
    if extra:
        tail += "\n\n" + extra
    send(uid, tail)
    return True


def send_file(chat_id, name, blob, caption=None):
    try:
        r = requests.post(API + "/sendDocument",
                          data={"chat_id": chat_id, "caption": caption or ""},
                          files={"document": (name, blob)}, timeout=60)
        return bool(r.json().get("ok"))
    except Exception as e:
        log.warning("sendDocument: %s", e)
        return False


def dump_db(chat_id):
    if not store.ON:
        send(chat_id, "Сховище вимкнене, DATABASE_URL не заданий.")
        return
    blob = store.export_all()
    name = "iryna-bot-" + time.strftime("%Y-%m-%d-%H%M") + ".json"
    if not send_file(chat_id, name, blob, "Вивантаження бази. Тримай як бекап."):
        send(chat_id, "Не вдалося надіслати файл.")


def stats_text():
    if not store.ON:
        return "Сховище вимкнене, DATABASE_URL не заданий."
    s = store.stats()
    users = (s["users"] or {}).get("n", 0)
    magnet = (s["magnet"] or {}).get("n", 0)
    paid = s["paid"] or {}
    lines = ["Стартів: " + str(users), "Забрали магніт: " + str(magnet),
             "Оплат: " + str(paid.get("n", 0)) + " на " + str(paid.get("uah", 0)) + " грн", "", "Мітки:"]
    for r in s["by_tag"] or []:
        lines.append("  " + r["tag"] + ": " + str(r["n"]))
    return "\n".join(lines)


# ---------- задачник ----------

def parse_tasks(text):
    items = []
    for line in (text or "").split("\n"):
        m = TASK_RE.match(line.strip())
        if m:
            items.append({"done": "✅" in m.group(1), "n": int(m.group(2)), "t": m.group(3).strip()})
    return items


def render_tasks(name, items):
    left = [i for i in items if not i["done"]]
    head = "Задачі, " + name + "\n" + "Відкрито: " + str(len(left)) + " з " + str(len(items)) + "\n\n"
    body = []
    first = True
    for i in items:
        if i["done"]:
            body.append("✅ #" + str(i["n"]) + " " + i["t"])
        elif first:
            body.append("▶️ #" + str(i["n"]) + " " + i["t"] + "   ← наступна")
            first = False
        else:
            body.append("▫️ #" + str(i["n"]) + " " + i["t"])
    foot = ("\n\nВсе, що стосується задач, просто надсилайте сюди: фото, схеми, відео, правки. "
            "Я передам далі.\n\nЩоб додати задачу, напишіть плюс і текст.")
    return head + "\n".join(body) + foot


def tasks_kb(items):
    rows = []
    for i in items:
        if not i["done"]:
            rows.append([{"text": "Готово: " + i["t"][:40], "callback_data": "td:" + str(i["n"])}])
        if len(rows) >= 8:
            break
    return {"inline_keyboard": rows} if rows else None


def pinned_of(uid):
    chat = api("getChat", chat_id=uid) or {}
    pin = chat.get("pinned_message") or {}
    return pin.get("message_id"), pin.get("text")


def items_of(owner):
    """Список власника з бази у форматі, який розуміє render_tasks."""
    return [{"done": r["done"], "n": r["n"], "t": r["text"]} for r in (store.tasks_of(owner) or [])]


def seed_once(uid, owner):
    """
    Разова заливка списку в базу. Спершу пробуємо забрати те, що вже висить
    у закріпі, щоб не втратити пункти, додані до переїзду. Якщо там порожньо,
    беремо SEED.
    """
    if store.tasks_of(owner):
        return
    mid, text = pinned_of(uid)
    old = parse_tasks(text)
    for i in old or []:
        r = store.add_task(owner, i["t"])
        if r and i["done"]:
            store.close_task(owner, r["n"])
    if not old:
        store.seed_tasks(owner, SEED.get(owner, []))
    if mid:
        store.set_user(uid, tasks_msg=mid)


def paint_tasks(uid, owner):
    """Малює список у закріпленому повідомленні. База це джерело правди, закріп це вітрина."""
    items = items_of(owner)
    text = render_tasks(owner, items)
    kb = tasks_kb(items)
    u = store.get_user(uid) or {}
    mid = u.get("tasks_msg")
    if not mid:
        mid, _ = pinned_of(uid)
    if mid and api("editMessageText", chat_id=uid, message_id=mid, text=text, reply_markup=kb):
        return
    m = api("sendMessage", chat_id=uid, text=text, reply_markup=kb, disable_web_page_preview=True)
    if m:
        api("pinChatMessage", chat_id=uid, message_id=m.get("message_id"), disable_notification=True)
        store.set_user(uid, tasks_msg=m.get("message_id"))


def show_tasks(uid, owner):
    seed_once(uid, owner)
    paint_tasks(uid, owner)


def add_task(uid, owner, text, by=None):
    seed_once(uid, owner)
    r = store.add_task(owner, text, created_by=by)
    paint_tasks(uid, owner)
    return r["n"] if r else 0


def close_task(uid, owner, n):
    r = store.close_task(owner, n)
    paint_tasks(uid, owner)
    return r["text"] if r else ""


@app.post("/" + SECRET)
def hook():
    upd = request.get_json(silent=True) or {}
    try:
        if "message" in upd:
            m = upd["message"]
            chat_id = m["chat"]["id"]
            u = m.get("from", {})
            uid = u.get("id")
            if u.get("is_bot"):
                return "ok"
            text = (m.get("text") or "").strip()
            doc = m.get("document")
            if doc and uid == ADMIN_ID:
                send(chat_id, "file_id цього файлу:\n" + doc.get("file_id", "?"))
                return "ok"
            if uid == ADMIN_ID and text.startswith("/export"):
                dump_db(chat_id)
                return "ok"
            if uid == ADMIN_ID and text.startswith("/stats"):
                send(chat_id, stats_text())
                return "ok"
            if uid in TEAM:
                store.touch_user(u, role="admin" if uid == ADMIN_ID else "ira")
                if not team_on(uid):
                    if text.startswith("/start"):
                        send(chat_id, "Задачник поки вимкнений.")
                    return "ok"
                name = TEAM[uid]
                if text.startswith("/todo") or text.lower() in ("задачі", "задачи"):
                    show_tasks(uid, name)
                    return "ok"
                if text.startswith("++") and uid == ADMIN_ID and IRA_ID:
                    body = text[2:].strip()
                    if body:
                        n = add_task(IRA_ID, "Іра", body, by=uid)
                        send(chat_id, "Додав Ірі задачу #" + str(n))
                    return "ok"
                if text.startswith("+"):
                    body = text[1:].strip()
                    if body:
                        n = add_task(uid, name, body, by=uid)
                        send(chat_id, "Додав задачу #" + str(n))
                    return "ok"
                if text.startswith("/start"):
                    send(chat_id, "Задачник тут. Напишіть /todo, і я покажу відкриті задачі.")
                    return "ok"
                for cid in NOTIFY_IDS:
                    if cid == uid:
                        continue
                    api("forwardMessage", chat_id=cid, from_chat_id=chat_id,
                        message_id=m.get("message_id"))
                    send(cid, "Від " + name + ", вище")
                if uid != ADMIN_ID:
                    send(chat_id, "Отримала, передаю далі ❤️")
                return "ok"
            if text.startswith("/start"):
                parts = text.split(None, 1)
                src = parts[1].strip()[:64] if len(parts) > 1 else ""
                rec = store.touch_user(u, source_tag=src) or {}
                store.log_event(uid, "start", {"tag": src})
                if rec.get("is_new", True):
                    notify("Новий у боті: " + who(u) + "\nМітка: " + (src or "без мітки"))
                send(chat_id, HELLO, magnet_kb())
            else:
                store.touch_user(u)
                store.log_event(uid, "message", {"text": text[:300]})
                notify("Повідомлення в боті від " + who(u) + ":\n" + (text or "[не текст]"))
                send(chat_id, "Прийняла, зараз подивлюсь і відповім ❤️")
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            api("answerCallbackQuery", callback_query_id=cq["id"])
            data = cq.get("data") or ""
            chat_id = cq["message"]["chat"]["id"]
            u = cq.get("from", {})
            uid = u.get("id")
            if data.startswith("td:") and uid in TEAM and team_on(uid):
                n = int(data.split(":")[1])
                title = close_task(uid, TEAM[uid], n)
                for cid in NOTIFY_IDS:
                    if cid != uid:
                        send(cid, TEAM[uid] + " закрила задачу: " + title if uid == IRA_ID
                             else TEAM[uid] + " закрив задачу: " + title)
                return "ok"
            if data == "magnet":
                give_magnet(chat_id)
                store.mark_magnet(uid)
                store.log_event(uid, "magnet")
            elif data == "guide":
                store.log_event(uid, "guide_open")
                send(chat_id, GUIDE_INTRO, tiers_kb())
            elif data in TIERS:
                t = TIERS[data]
                code = order_code(uid, data)
                store.add_purchase(uid, "guide", tier=data, order_code=code, amount_uah=t["uah"])
                store.log_event(uid, "tier_pick", {"tier": data, "code": code})
                body = t["text"]
                if PAY_URL:
                    body += ("\n\nТисніть кнопку і у коментарі до платежу впишіть код:\n" + code +
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
                       + who(u) + "\nКод: " + code, give_kb(uid, data))
            elif data.startswith("paid:") and TEST_MODE:
                tier = data.split(":")[1]
                code = order_code(uid, tier)
                ok = give_guide(uid, tier)
                if not ok:
                    send(chat_id, "Тест: файл ще не підключений, впиши GUIDE_FILE_ID.")
                store.mark_paid(code)
                if ok:
                    store.mark_delivered(code)
                store.log_event(uid, "pay_test", {"tier": tier, "code": code, "ok": ok})
                notify("ТЕСТ оплати: " + TIERS.get(tier, {}).get("name", tier) + "\n" + who(u))
            elif data.startswith("give:") and uid in NOTIFY_IDS:
                parts = (data.split(":") + ["", ""])[:3]
                target = int(parts[1])
                ok = give_guide(target, parts[2])
                code = order_code(target, parts[2]) if parts[2] else None
                if ok and code:
                    store.mark_paid(code)
                    store.mark_delivered(code)
                store.log_event(target, "give_manual", {"tier": parts[2], "by": uid, "ok": ok})
                send(chat_id, "Видано" if ok else "Не вдалося, перевір GUIDE_FILE_ID")
    except Exception as e:
        log.exception("update failed: %s", e)
    return "ok"


@app.get("/")
def health():
    # У базу звідси не ходимо ніколи: keepalive стукає сюди раз на 10 хвилин,
    # і кожен такий запит будив би Neon.
    return "ok"


@app.get("/db/" + SECRET)
def db_status():
    if not store.DSN:
        return "DATABASE_URL не заданий, бот працює без памʼяті"
    if not store.ON:
        return "DATABASE_URL заданий, але psycopg не встановлений"
    r = store.q("select now() as t", fetch="one")
    if not r:
        return "база не відповідає, дивись логи"
    return "<pre>ok " + str(r["t"]) + "\n\n" + stats_text() + "</pre>"


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
        out = [j.get("title", "?") + "  ->  " + j.get("id", "?") for j in r.json().get("jars", [])]
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
    code = "IR" + m.group(1).upper() + "-" + m.group(2)
    need = TIERS.get(tier, {}).get("uah", 0) * 100
    if amount < need * 0.9:
        store.log_event(uid, "pay_short", {"code": code, "uah": amount // 100, "need": need // 100})
        notify("Оплата " + str(amount // 100) + " грн за кодом " + code
               + ", а треба " + str(need // 100) + " грн. Гайд не видано.")
        return
    store.mark_paid(code, amount // 100)
    ok = give_guide(uid, tier)
    if ok:
        store.mark_delivered(code)
    store.log_event(uid, "pay_ok" if ok else "pay_undelivered", {"code": code, "uah": amount // 100})
    notify(("Оплата " + str(amount // 100) + " грн, код " + code + ". Гайд видано автоматично.")
           if ok else ("Оплата " + str(amount // 100) + " грн, код " + code
                       + ", але файл не пішов. Перевір GUIDE_FILE_ID."))


def mono_poll():
    """
    Виписка читається щохвилини з чимось, а в базу ходимо тільки за новою
    транзакцією. Інакше цикл тримав би Neon прокинутим цілодобово.
    seen це фільтр першого рівня, mono_tx у базі другого: він переживає
    рестарт і не дає двом воркерам видати гайд двічі.
    """
    seen = set()
    ever = None    # чи бот колись уже читав цю банку
    first = True   # перший прохід у цьому процесі
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
                if ever is None:
                    ever = store.kv_get("mono_primed") == "1"
                if not store.claim_tx(tid, tx.get("amount"), tx.get("comment")):
                    continue
                if ever or not first:
                    handle_tx(tx)
            if first:
                first = False
                if ever is False:
                    store.kv_set("mono_primed", 1)
                    ever = True
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
