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


COMMIT = (os.getenv("RENDER_GIT_COMMIT", "") or "")[:7]


def status_text():
    """
    Рядок стану для Yaro. Спершу те, що ламається, потім те, що заробляє.
    Прапорці словами: галочка не каже, добре це чи погано.
    Комміт тут не прикраса, сьогодні ми двічі не знали, чи деплой доїхав.
    """
    d = store.stats_day() if store.ON else None
    if not store.ON:
        db = "вимкнена, DATABASE_URL не заданий"
    elif not d or not d.get("now"):
        db = "НЕ ВІДПОВІДАЄ, дивись логи"
    else:
        db = "жива"
    lines = [
        "База: " + db,
        "Комміт: " + (COMMIT or "невідомий, RENDER_GIT_COMMIT не задана"),
        "Тестовий режим: " + ("увімкнений" if TEST_MODE else "вимкнений"),
        "Банка: " + ("підключена" if PAY_URL else "не підключена"),
        "Бот Іри: " + ("увімкнений" if IRA_ON else "вимкнений"),
        "Гайд: " + ("на місці" if GUIDE_FILE_ID else "GUIDE_FILE_ID не заданий"),
    ]
    if d and d.get("now"):
        paid = d.get("paid") or {}
        lines.append("")
        lines.append("За добу: стартів " + str((d.get("starts") or {}).get("n", 0))
                     + " · магніт " + str((d.get("magnet") or {}).get("n", 0))
                     + " · оплат " + str(paid.get("n", 0)) + " на " + str(paid.get("uah", 0)) + " грн")
        lines.append("Нерозкладеного: " + str(store.inbox_count())
                     + " · відкритих задач: " + str(len(store.tasks_of("Яро", only_open=True) or [])))
    return "\n".join(lines)


BTN_INBOX, BTN_STATUS = "Нерозкладене", "Стан"
BTN_MINE, BTN_IRA = "Мої задачі", "Задачі Іри"


def admin_kb():
    """Лічильник має право бути гучним тільки на нерозкладеному."""
    n = store.inbox_count() if store.ON else 0
    inbox = BTN_INBOX + (" · " + str(n) if n else "")
    return {"keyboard": [[{"text": inbox}, {"text": BTN_STATUS}],
                         [{"text": BTN_MINE}, {"text": BTN_IRA}]],
            "resize_keyboard": True, "is_persistent": True}


def sync_commands():
    """
    Команди задаються з областю дії, тому клієнтка не побачить у меню
    ні /inbox, ні /status. Це чистіше за фільтрацію по id всередині хендлерів.
    """
    try:
        api("setMyCommands", commands=[], scope={"type": "default"})
        if ADMIN_ID:
            api("setMyCommands", scope={"type": "chat", "chat_id": ADMIN_ID}, commands=[
                {"command": "now", "description": "що зараз, одна задача"},
                {"command": "todo", "description": "мої задачі"},
                {"command": "inbox", "description": "нерозкладене від Іри"},
                {"command": "status", "description": "стан бота і цифри за добу"},
                {"command": "export", "description": "вивантажити базу"},
            ])
        if IRA_ID:
            api("setMyCommands", scope={"type": "chat", "chat_id": IRA_ID}, commands=[
                {"command": "todo", "description": "мої задачі"},
            ])
    except Exception as e:
        log.warning("setMyCommands: %s", e)


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


PROJECTS = [("ira", "Іра"), ("eng", "Англійська"), ("mstr", "Майстри"), ("byt", "Побут")]
PROJ_LABEL = dict(PROJECTS)
PROJ_KEY = {}
for _k, _v in PROJECTS:
    PROJ_KEY[_k] = _k
    PROJ_KEY[_v.lower()] = _k
TAG_RE = re.compile(r"(?:^|\s)#([^\s#]+)")


def pick_project(text):
    """Витягує #мітку з тексту. Повертає текст без мітки і ключ проєкту."""
    key = None
    def take(m):
        nonlocal key
        cand = PROJ_KEY.get(m.group(1).strip().lower())
        if cand and not key:
            key = cand
            return " "
        return m.group(0)
    clean = re.sub(r"\s{2,}", " ", TAG_RE.sub(take, text or "")).strip()
    return (clean or text or "").strip(), key


def proj_name(key):
    return PROJ_LABEL.get(key or "", "інбокс")


def render_tasks(owner, rows):
    rows = rows or []
    open_rows = [r for r in rows if not r["done"]]
    head = ("Задачі, " + owner + "\nВідкрито: " + str(len(open_rows)) + " з " + str(len(rows)))
    if not open_rows:
        return head + "\n\nПорожньо. Просто надішліть текст, і він стане задачею."
    groups = {}
    for r in open_rows:
        groups.setdefault(r.get("project") or "", []).append(r)
    order = [k for k, _ in PROJECTS if k in groups]
    if "" in groups:
        order.insert(0, "")
    body = []
    for k in order:
        body.append("\n" + proj_name(k).upper())
        for r in groups[k]:
            mark = "💤" if r.get("deferred_at") else "▫️"
            body.append(mark + " #" + str(r["n"]) + " " + r["text"])
    foot = ("\n\nНадішліть будь-який текст, і він стане задачею в інбоксі. "
            "Мітка проєкту через решітку: #іра, #англійська, #майстри, #побут.")
    return head + "\n" + "\n".join(body) + foot


def tasks_kb(rows):
    kb = [[{"text": "Що зараз", "callback_data": "tnow"}]]
    for r in [x for x in (rows or []) if not x["done"]][:6]:
        kb.append([{"text": "Готово: " + r["text"][:38], "callback_data": "td:" + str(r["n"])}])
    return {"inline_keyboard": kb}


def proj_kb(n, with_delete=True):
    row = [{"text": PROJ_LABEL[k], "callback_data": "tp:" + str(n) + ":" + k} for k, _ in PROJECTS]
    kb = [row[:2], row[2:]]
    if with_delete:
        kb.append([{"text": "Це не задача, прибрати", "callback_data": "tdl:" + str(n)}])
    return {"inline_keyboard": kb}


def now_kb(r):
    n = str(r["n"])
    return {"inline_keyboard": [
        [{"text": "Готово", "callback_data": "td:" + n},
         {"text": "Пізніше", "callback_data": "tdf:" + n}],
        [{"text": "Наступна", "callback_data": "tnow"},
         {"text": "Проєкт", "callback_data": "tpk:" + n}],
    ]}


def render_now(owner, r):
    if not r:
        return "Відкритих задач немає. Порожньо і добре."
    left = len(store.tasks_of(owner, only_open=True) or [])
    head = "Зараз · " + proj_name(r.get("project"))
    tail = "\n\nВідкрито всього: " + str(left)
    return head + "\n\n#" + str(r["n"]) + " " + r["text"] + tail


def show_now(uid, owner, message_id=None):
    r = store.next_task(owner)
    text = render_now(owner, r)
    kb = now_kb(r) if r else None
    if message_id and api("editMessageText", chat_id=uid, message_id=message_id,
                          text=text, reply_markup=kb):
        return
    send(uid, text, kb)


def pinned_of(uid):
    chat = api("getChat", chat_id=uid) or {}
    pin = chat.get("pinned_message") or {}
    return pin.get("message_id"), pin.get("text")


def items_of(owner):
    return store.tasks_of(owner) or []


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


def add_task(uid, owner, text, by=None, project=None):
    seed_once(uid, owner)
    body, tag = pick_project(text)
    r = store.add_task(owner, body, created_by=by, project=project or tag)
    paint_tasks(uid, owner)
    return r if r else None


def close_task(uid, owner, n):
    r = store.close_task(owner, n)
    paint_tasks(uid, owner)
    return r["text"] if r else ""


def catch_task(uid, owner, text, by=None):
    """
    Ловля без церемоній: будь-який текст стає задачею в інбоксі, а розкладання
    по проєктах відбувається потім, одним тапом. Якщо вимагати проєкт наперед,
    ловити перестануть.
    """
    r = add_task(uid, owner, text, by=by)
    if not r:
        send(uid, "Не зміг записати, база не відповіла.")
        return
    where = proj_name(r.get("project"))
    send(uid, "Записав #" + str(r["n"]) + " у «" + where + "»\n" + r["text"],
         proj_kb(r["n"]))


# ---------- прийом матеріалів від Іри ----------

BUCKETS = [("guide", "правка в гайд"), ("kanal", "в канал"),
           ("task", "в задачі"), ("keep", "просто зберегти")]
BUCKET_LABEL = dict(BUCKETS)
GUIDE_WORDS = ("сторінк", "заміни", "заміна", "прибери", "прибрати", "додай",
               "додати", "виправ", "правк", "абзац", "схем")

IRA_HELLO = (
    "Привіт ❤️\n"
    "Сюди можна кидати все: правки до гайду, фото зі зйомок, беки, голосові. "
    "Я передам Yaro, розбирати нічого не треба.\n"
    "Внизу дві кнопки: задачі і додати задачу."
)
IRA_KB = {"keyboard": [[{"text": "Мої задачі"}, {"text": "Додати"}]],
          "resize_keyboard": True, "is_persistent": True}

FILE_KINDS = (
    ("photo", "фото"), ("video", "відео"), ("document", "документ"),
    ("voice", "голосове"), ("audio", "аудіо"), ("video_note", "кружечок"),
    ("animation", "гіфка"), ("sticker", "стікер"),
)
SEND_BY_KIND = {
    "фото": ("sendPhoto", "photo"), "відео": ("sendVideo", "video"),
    "документ": ("sendDocument", "document"), "голосове": ("sendVoice", "voice"),
    "аудіо": ("sendAudio", "audio"), "кружечок": ("sendVideoNote", "video_note"),
    "гіфка": ("sendAnimation", "animation"), "стікер": ("sendSticker", "sticker"),
}


def extract_file(m):
    """Повертає (тип, file_id, file_unique_id) або (None, None, None)."""
    for key, label in FILE_KINDS:
        v = m.get(key)
        if not v:
            continue
        if key == "photo":
            v = v[-1]
        return label, v.get("file_id"), v.get("file_unique_id")
    return None, None, None


def mat_kb(target, kind, caption):
    """Порядок кнопок підказує ймовірне, але не вирішує за Yaro."""
    order = [k for k, _ in BUCKETS]
    low = (caption or "").lower()
    if any(w in low for w in GUIDE_WORDS):
        order.remove("guide"); order.insert(0, "guide")
    elif kind in ("фото", "відео") and not low:
        order.remove("kanal"); order.insert(0, "kanal")
    btns = [{"text": BUCKET_LABEL[k], "callback_data": "mb:" + target + ":" + k} for k in order]
    return {"inline_keyboard": [btns[:2], btns[2:]]}


try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception as _e:            # немає бази часових поясів у образі
    PARIS = None
    log.warning("Europe/Paris недоступна (%s), час буде в UTC", _e)


def hhmm():
    """
    Час Yaro, а не сервера. Підміну змінної TZ навмисно не використовуємо:
    вона мовчки дає неправильний час там, де немає бази поясів.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return (now.astimezone(PARIS) if PARIS else now).strftime("%H:%M")


def mat_card(target, kind, caption, n=1, src="Від Іри"):
    kind_word = ("альбом " + str(n)) if n > 1 else (kind or "текст")
    head = src + " · " + hhmm() + " · " + kind_word
    body = ("\n" + caption[:400]) if caption else ""
    for cid in NOTIFY_IDS:
        api("sendMessage", chat_id=cid, text=head + body,
            reply_markup=mat_kb(target, kind, caption), disable_web_page_preview=True)


_albums = {}
_albums_lock = threading.Lock()


def album_touch(gid, chat_id, kind, caption, src="Від Іри", reply=True):
    """
    Телеграм шле кожне фото альбому окремим апдейтом. Без цього збирання
    бот відповідав би Ірі двадцять разів підряд на один альбом.
    """
    with _albums_lock:
        a = _albums.get(gid)
        if a is None:
            a = {"n": 0, "chat_id": chat_id, "kind": kind, "caption": caption,
                 "src": src, "reply": reply, "timer": None}
            _albums[gid] = a
        a["n"] += 1
        if caption and not a["caption"]:
            a["caption"] = caption
        if a["timer"]:
            a["timer"].cancel()
        t = threading.Timer(3.0, album_flush, args=(gid,))
        t.daemon = True
        a["timer"] = t
        t.start()


def album_flush(gid):
    with _albums_lock:
        a = _albums.pop(gid, None)
    if not a:
        return
    try:
        if a.get("reply", True):
            send(a["chat_id"], "Прийняла всі " + str(a["n"]) + " ❤️ Передаю Yaro.")
        mat_card("g:" + str(gid), a["kind"], a["caption"], n=a["n"], src=a.get("src", "Від Іри"))
    except Exception as e:
        log.warning("album_flush: %s", e)


def is_forwarded(m):
    return bool(m.get("forward_origin") or m.get("forward_from")
                or m.get("forward_from_chat") or m.get("forward_date"))


def take_material(m, chat_id, uid, src="Від Іри", reply=True):
    """
    Від Іри не вимагається нічого, крім кинути файл, розкладає Yaro.
    Пересланим самим Yaro користуємось так само: те, що він набрав руками,
    це його задача, а те, що переслав, це чужий матеріал.
    """
    kind, fid, fuid = extract_file(m)
    caption = (m.get("caption") or m.get("text") or "").strip()
    gid = m.get("media_group_id")
    if not fid:
        # Текстова правка це теж матеріал, і вона не має губитись через те,
        # що до неї не прикріплений файл.
        kind, fid, fuid = "текст", "", None
    row = store.add_asset(uid, fid, kind, caption=caption or None,
                          media_group=str(gid) if gid else None, file_unique_id=fuid)
    for cid in NOTIFY_IDS:
        if cid != uid:
            api("forwardMessage", chat_id=cid, from_chat_id=chat_id, message_id=m.get("message_id"))
    if gid:
        album_touch(str(gid), chat_id, kind, caption, src=src, reply=reply)
        return
    if reply:
        if kind == "голосове":
            send(chat_id, "Прийняла голосове ❤️ Передаю Yaro.")
        else:
            send(chat_id, "Прийняла ❤️ Передаю Yaro.")
    target = ("a:" + str(row["id"])) if row else "t:0"
    mat_card(target, kind or "", caption, src=src)


def sort_material(target, bucket, by):
    """Повертає (скільки карток, підпис) після розкладання."""
    kind, key = (target.split(":", 1) + [""])[:2]
    caption = ""
    cnt = 0
    if kind == "g":
        rows = store.assets_of_group(key) or []
        caption = next((r["caption"] for r in rows if r.get("caption")), "")
        cnt = store.set_bucket_group(key, bucket)
    elif kind == "a":
        r = store.set_bucket(int(key), bucket)
        if r:
            cnt, caption = 1, r.get("caption") or ""
    if bucket == "task":
        body = (caption or "матеріал від Іри")[:200]
        store.add_task("Яро", body, created_by=by, project="ira")
    return cnt, caption


def show_inbox(chat_id):
    n = store.inbox_count()
    if not n:
        send(chat_id, "Нерозкладеного немає.")
        return
    r = store.inbox_next()
    if not r:
        send(chat_id, "Нерозкладених " + str(n) + ", але картку дістати не вдалось.")
        return
    if r.get("media_group"):
        target = "g:" + r["media_group"]
        cnt = len(store.assets_of_group(r["media_group"]) or [])
    else:
        target = "a:" + str(r["id"])
        cnt = 1
    method, field = SEND_BY_KIND.get(r.get("file_kind") or "", (None, None))
    if r.get("file_id") and method:
        api(method, chat_id=chat_id, **{field: r["file_id"]})
    send(chat_id, "Нерозкладених: " + str(n) + "\n" + (r.get("caption") or ""),
         mat_kb(target, r.get("file_kind") or "", r.get("caption") or ""))


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
            text = (m.get("text") or m.get("caption") or "").strip()
            doc = m.get("document")
            if doc and uid == ADMIN_ID and not is_forwarded(m):
                # Свій файл віддаємо як file_id, це службове. Переслане йде
                # звичайним шляхом матеріалу, інакше правка Іри в PDF
                # перетворилась би на рядок службового тексту.
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
                if text.startswith("/now") or text.lower() in ("що зараз", "шо зараз"):
                    seed_once(uid, name)
                    show_now(uid, name)
                    return "ok"
                if text.startswith("++") and uid == ADMIN_ID and IRA_ID:
                    body = text[2:].strip()
                    if body:
                        r = add_task(IRA_ID, "Іра", body, by=uid)
                        send(chat_id, "Додав Ірі задачу #" + str(r["n"] if r else "?"))
                    return "ok"
                if text.startswith("+"):
                    body = text[1:].strip()
                    if body:
                        r = add_task(uid, name, body, by=uid)
                        send(chat_id, "Додав задачу #" + str(r["n"] if r else "?"))
                    return "ok"
                if text.startswith("/start"):
                    if uid == ADMIN_ID:
                        send(chat_id, "Задачник тут. Кнопки внизу, або командами: /now одна задача, "
                                      "/todo список, /inbox нерозкладене, /status стан. "
                                      "Будь-який інший текст я запишу в інбокс.", admin_kb())
                    else:
                        send(chat_id, IRA_HELLO, IRA_KB)
                    return "ok"
                if uid == ADMIN_ID and (text.startswith("/inbox") or text.startswith(BTN_INBOX)):
                    show_inbox(chat_id)
                    return "ok"
                if uid == ADMIN_ID and (text.split(" ")[0] == "/status"
                                        or text.lower() in ("стан", BTN_STATUS.lower())):
                    send(chat_id, status_text(), admin_kb())
                    return "ok"
                if uid == ADMIN_ID and text == BTN_MINE:
                    show_tasks(uid, name)
                    return "ok"
                if uid == ADMIN_ID and text == BTN_IRA:
                    rows = store.tasks_of("Іра") or []
                    if not rows:
                        send(chat_id, "У Іри задач немає.")
                    else:
                        # Тільки перегляд: закривати її задачі за неї означає показати їй
                        # закритим те, чого вона не робила.
                        send(chat_id, render_tasks("Іра", rows) + "\n\nЦе перегляд. "
                             "Щоб додати їй задачу, напишіть два плюси і текст.")
                    return "ok"
                if uid != ADMIN_ID:
                    low = text.lower()
                    if low in ("мої задачі", "мои задачи"):
                        show_tasks(uid, name)
                        return "ok"
                    if low in ("додати", "добавить"):
                        send(chat_id, "Напишіть задачу з плюсом попереду, наприклад: +купити фон")
                        return "ok"
                    take_material(m, chat_id, uid)
                    return "ok"
                if uid == ADMIN_ID:
                    # Набрав руками це своя думка, тобто задача.
                    # Переслав це чужий матеріал: правки Іри по гайду приходять
                    # пачками, і двадцять задач з них зробили б список непридатним.
                    # Рішення не вгадуємо: у картці матеріалу є кнопка «в задачі».
                    if is_forwarded(m) or extract_file(m)[1]:
                        take_material(m, chat_id, uid, src="Переслане", reply=False)
                    elif text and not text.startswith("/"):
                        seed_once(uid, name)
                        catch_task(uid, name, text, by=uid)
                    elif not text:
                        send(chat_id, "Не зрозумів, що з цим робити.")
                    return "ok"
                take_material(m, chat_id, uid)
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
                # Без обіцянки часу: це повідомлення йде в сповіщення Yaro, а не до Іри,
                # тому «зараз відповім» тут було обіцянкою, якої ніхто не виконує.
                send(chat_id, "Прийняла ❤️ Якщо це про зйомку, напишіть в інстаграм, "
                              "там відповідаю швидше: @iryna_rul_photographer")
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            api("answerCallbackQuery", callback_query_id=cq["id"])
            data = cq.get("data") or ""
            chat_id = cq["message"]["chat"]["id"]
            u = cq.get("from", {})
            uid = u.get("id")
            if data.startswith("mb:") and uid in NOTIFY_IDS:
                parts = data.split(":")
                target, bucket = parts[1] + ":" + parts[2], parts[3]
                cnt, caption = sort_material(target, bucket, uid)
                mid = cq["message"].get("message_id")
                label = BUCKET_LABEL.get(bucket, bucket)
                left = store.inbox_count()
                # Картка не зникає, а перепідписується: видно, куди пішло.
                head = (cq["message"].get("text") or "Від Іри").split("\n")[0]
                txt = head + " · → " + label + "\nНерозкладених лишилось: " + str(left)
                api("editMessageText", chat_id=chat_id, message_id=mid, text=txt,
                    reply_markup={"inline_keyboard": [[
                        {"text": "Наступне нерозкладене", "callback_data": "mnx"}]]} if left else None)
                return "ok"
            if data == "mnx" and uid in NOTIFY_IDS:
                show_inbox(chat_id)
                return "ok"
            if data[:3] in ("td:", "tdf", "tpk", "tp:", "tdl", "tno") and uid in TEAM and team_on(uid):
                owner = TEAM[uid]
                mid = cq["message"].get("message_id")
                pinned = (store.get_user(uid) or {}).get("tasks_msg")
                on_now = mid and mid != pinned

                if data == "tnow":
                    show_now(uid, owner, mid if on_now else None)
                    return "ok"

                n = int(data.split(":")[1])

                if data.startswith("td:"):
                    title = close_task(uid, owner, n)
                    for cid in NOTIFY_IDS:
                        if cid != uid:
                            send(cid, owner + (" закрила задачу: " if uid == IRA_ID else " закрив задачу: ") + title)
                    if on_now:
                        show_now(uid, owner, mid)
                    return "ok"

                if data.startswith("tdf:"):
                    store.defer_task(owner, n)
                    paint_tasks(uid, owner)
                    if on_now:
                        show_now(uid, owner, mid)
                    return "ok"

                if data.startswith("tpk:"):
                    api("editMessageReplyMarkup", chat_id=uid, message_id=mid,
                        reply_markup=proj_kb(n, with_delete=False))
                    return "ok"

                if data.startswith("tp:"):
                    key = data.split(":")[2]
                    r = store.set_task_project(owner, n, key)
                    paint_tasks(uid, owner)
                    api("editMessageText", chat_id=uid, message_id=mid,
                        text="#" + str(n) + " " + (r["text"] if r else "") + "\n→ " + proj_name(key),
                        reply_markup={"inline_keyboard": [[
                            {"text": "Готово", "callback_data": "td:" + str(n)},
                            {"text": "Що зараз", "callback_data": "tnow"}]]})
                    return "ok"

                if data.startswith("tdl:"):
                    r = store.delete_task(owner, n)
                    paint_tasks(uid, owner)
                    api("editMessageText", chat_id=uid, message_id=mid,
                        text="Прибрав: " + (r["text"][:80] if r else "#" + str(n)))
                    return "ok"
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
threading.Thread(target=sync_commands, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
