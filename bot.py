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
# запасна адреса: без неї самопінг не стартує і сервіс засинає через 15 хвилин
BASE_URL      = (os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
                 or "https://iryna-bot.onrender.com")


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
    "Привіт, це Ірина Руль ♥️\n\n"
    "Тут моя добірка «Три схеми світла з одного сетапу».\n"
    "Три різні картинки за одну зйомку, без докупки обладнання.\n\n"
    "Тисніть кнопку, надішлю файл."
)
AFTER = (
    "Готово, файл вище ♥️\n\n"
    "Спробуйте на найближчій зйомці, це пʼять хвилин на студії.\n\n"
    "У каналі «Iryna Rul | для своїх» розбираю світло і ретуш детальніше.\n"
    "Хочете всі схеми, а не три, тисніть другу кнопку."
)
GUIDE_INTRO = (
    "Повний гайд «Світло» ♥️\n\n"
    "Усі мої робочі схеми, від чистої комерції до кольору.\n"
    "Кожна з розстановкою, налаштуваннями і кадром зі зйомки.\n\n"
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
    # Найдорожчий глухий кут лійки: людина заплатила, а файл не прийшов.
    # Кнопка веде до живої людини, і обіцянку виконує Yaro, а не Іра.
    rows.append([{"text": "Оплатив, а файлу немає", "callback_data": "noget:" + tier}])
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
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ♥️")
        return
    r = api("sendDocument", chat_id=chat_id, document=MAGNET_URL)
    if not r:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ♥️")
        return
    send(chat_id, AFTER, after_kb())


NOGET_TEXT = ("Перевірю вручну, зазвичай це кілька хвилин ♥️ "
              "Файл прийде сюди, нічого робити не треба.")
BROKEN_FILE_TEXT = ("Щось пішло не так з файлом ♥️ "
                    "Уже розбираюсь, надішлю сюди за кілька хвилин.")
NUDGE_TEXT = ("Якщо оплата пройшла, а файл не дійшов, натисніть кнопку нижче, "
              "я перевірю вручну ♥️")


def nudge_later(uid, tier, code, delay=900):
    """
    Через пʼятнадцять хвилин нагадуємо про кнопку тому, хто заплатив і мовчить.
    Таймер, а не опитування бази: цикл, який ходив би в базу щохвилини,
    тримав би Neon прокинутим цілодобово і зʼїв би безкоштовний ліміт.
    """
    def fire():
        try:
            p = store.get_purchase(code)
            if p and p.get("status") == "new":
                send(uid, NUDGE_TEXT, {"inline_keyboard": [[
                    {"text": "Оплатив, а файлу немає", "callback_data": "noget:" + tier}]]})
        except Exception as e:
            log.warning("nudge: %s", e)
    t = threading.Timer(delay, fire)
    t.daemon = True
    t.start()


def give_guide(uid, tier):
    if not GUIDE_FILE_ID:
        send(uid, "Хвилинку, зараз надішлю файл ♥️")
        return False
    if not api("sendDocument", chat_id=uid, document=GUIDE_FILE_ID):
        return False
    tail = "Оплату бачу, гайд ваш назавжди ♥️"
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


def keepalive_state():
    """
    Render присипляє безкоштовний сервіс після 15 хвилин тиші, і тоді перше
    повідомлення чекає близько хвилини. Єдине, що цьому заважає, це самопінг,
    і досі не було способу дізнатись, чи він живий.
    """
    if not BASE_URL:
        return "НЕ СТЕРЕЖЕТЬСЯ, RENDER_EXTERNAL_URL не заданий, сервіс засинає"
    last = KEEPALIVE.get("last_ok")
    if not last:
        return "самопінг ще не відпрацював, перший буде за 10 хвилин після старту"
    mins = int((time.time() - last) / 60)
    tail = ", збоїв підряд: " + str(KEEPALIVE["fails"]) if KEEPALIVE["fails"] else ""
    return "самопінг живий, останній " + str(mins) + " хв тому" + tail


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
        "Сон сервісу: " + keepalive_state(),
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
                {"command": "blocks", "description": "блоки з матеріалом від Іри"},
                {"command": "ira", "description": "подивитись на бота її очима"},
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
    "Привіт ♥️\n"
    "Сюди можна кидати все: правки до гайду, фото зі зйомок, беки, голосові. "
    "Я передам Yaro, розбирати нічого не треба.\n"
    "Внизу дві кнопки: задачі і додати задачу."
)
IRA_KB = {"keyboard": [[{"text": "Матеріали"}],
                       [{"text": "Мої задачі"}, {"text": "Додати"}]],
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


# ---------- блоки: куди зараз падає матеріал ----------

KIND_LABEL = {"schema": "Схеми світла", "page": "Сторінки гайда",
              "kanal": "Канал", "other": "Інше"}

# Витягнуто з чинного PDF гайда від 28.08. Схеми 4 і 5 у гайді названі
# однаково, тому розрізняємо їх підзаголовком, інакше вибір за назвою
# перетворюється на вгадування.
# Схему 13 не сіємо: вона дубль восьмої, і в меню дала б дві однакові назви.
SCHEMAS = [
    (1, "Чистий білий фон"),
    (2, "Темний фон на циклорамі"),
    (3, "Білий фон з жорсткими тінями"),
    (4, "Темний фон з підсвіченою циклорамою, два джерела"),
    (5, "Темний фон з підсвіченою циклорамою, три джерела"),
    (6, "Білий фон, модель у тіні"),
    (7, "Контрове світло, модель у тіні"),
    (8, "Імітація денного світла"),
    (9, "Кольорова градація світла"),
    (10, "Контрове світло"),
    (11, "Жорстка тінь на фоні"),
    (12, "Мʼяке заповнення"),
]
PAGES = ["Обкладинка", "Сторінка знайомства", "База, налаштування камери",
         "Потужності джерел", "Шпаргалка", "Фінальна сторінка"]


def seed_catalog():
    rows = [("schema", str(n), t, n) for n, t in SCHEMAS]
    # Код обовʼязковий навіть сторінкам: NULL не конфліктує сам із собою,
    # тому без нього рядки дублювались би при кожному старті сервісу.
    rows += [("page", "p" + str(i + 1), t, i + 1) for i, t in enumerate(PAGES)]
    try:
        n = store.seed_blocks(rows)
        if n:
            log.info("засіяно блоків: %s", n)
    except Exception as e:
        log.warning("seed_catalog: %s", e)
PAUSE_AFTER = 1800  # тиша, після якої питаємо, чи продовжуємо
_pause = {}
_pause_lock = threading.Lock()
_asked_block = {}   # щоб питати «до якого блоку» один раз, а не на кожен файл


def block_name(b):
    if not b:
        return "Без блоку"
    if b.get("kind") == "schema" and b.get("code"):
        return "Схема " + str(b["code"]) + " · " + b["title"]
    return b["title"]


def block_card_text(b, paused=False):
    tally = store.block_tally(b["id"]) or []
    if tally:
        line = " · ".join(str(r["n"]) + " " + r["kind"] for r in tally)
    else:
        line = "поки порожньо"
    head = block_name(b)
    if paused:
        return head + "\nПрийнято: " + line + "\n\nПауза. Продовжуємо?"
    return head + "\nПрийнято: " + line


def block_card_kb(paused=False):
    if paused:
        return {"inline_keyboard": [[{"text": "Так, продовжуємо", "callback_data": "bgo"},
                                     {"text": "Обрати інше", "callback_data": "bmenu"}]]}
    return {"inline_keyboard": [[{"text": "Готово, наступне", "callback_data": "bdone"},
                                 {"text": "Змінити блок", "callback_data": "bmenu"}]]}


def kinds_kb():
    rows = []
    for r in (store.block_kinds() or []):
        rows.append([{"text": KIND_LABEL.get(r["kind"], r["kind"]) + " · " + str(r["n"]),
                      "callback_data": "bk:" + r["kind"]}])
    return {"inline_keyboard": rows} if rows else None


def blocks_kb(kind):
    rows, pair = [], []
    for b in (store.list_blocks(kind) or []):
        # Назва першою, номер після неї. Її «1., 2., 3.» це порядок у пачці,
        # а не номер схеми в гайді, і саме на цьому ми вже втратили роботу.
        label = (b["title"] + " · №" + str(b["code"])) if b.get("code") else b["title"]
        pair.append({"text": label[:32], "callback_data": "bs:" + str(b["id"])})
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([{"text": "Назад", "callback_data": "bmenu"}])
    return {"inline_keyboard": rows}


_last_edit = {}
_pending = {}
_edit_lock = threading.Lock()
EDIT_GAP = 3.0


def _flush_card(uid):
    with _edit_lock:
        _pending.pop(uid, None)
        _last_edit[uid] = time.time()
    refresh_block_card(uid, force=True)


def refresh_block_card(uid, paused=False, force=False):
    """
    Мовчазне оновлення: редагування не дає сповіщення. Саме тому бот не
    відповідає на кожен її файл, а просто перемальовує одну картку.

    Пересилання пачки з чату дає десятки повідомлень за секунди. Без стримування
    ми б довбали телеграм редагуваннями і впіймали обмеження на найважливішому
    сценарії. Тому не частіше разу на три секунди, плюс відкладений показ
    фінального стану, щоб остання цифра не загубилась.
    """
    b = store.active_block(uid)
    if not b:
        return
    if not (paused or force):
        with _edit_lock:
            now = time.time()
            last = _last_edit.get(uid, 0)
            if now - last < EDIT_GAP:
                # Відкладений показ ставимо один, а не по одному на кожне
                # пропущене оновлення, інакше пачка дасть пачку редагувань.
                if not _pending.get(uid):
                    _pending[uid] = True
                    t = threading.Timer(EDIT_GAP, _flush_card, args=(uid,))
                    t.daemon = True
                    t.start()
                return
            _last_edit[uid] = now
            _pending.pop(uid, None)
    mid = (store.get_user(uid) or {}).get("block_msg")
    if mid:
        api("editMessageText", chat_id=uid, message_id=mid,
            text=block_card_text(b, paused), reply_markup=block_card_kb(paused))


def ensure_card(uid, b):
    """
    Одна картка на екрані, хай там обраний блок чи ні. Без блоку вона просто
    показує, що прийнято, і нічого не питає: закріп чіпаємо лише тоді, коли
    вона сама обрала блок.
    """
    if b:
        refresh_block_card(uid)
        return
    ib = store.inbox_block()
    if not ib:
        return
    mid = (store.get_user(uid) or {}).get("block_msg")
    text = "Прийнято ♥️\n" + block_card_text(ib).split("\n", 1)[-1]
    if mid and api("editMessageText", chat_id=uid, message_id=mid, text=text):
        return
    m = api("sendMessage", chat_id=uid, text=text, disable_web_page_preview=True)
    if m:
        store.set_user(uid, block_msg=m.get("message_id"))


def touch_pause(uid):
    """Один таймер на людину: тиша довша за півгодини питає, чи продовжуємо."""
    with _pause_lock:
        t = _pause.get(uid)
        if t:
            t.cancel()
        t = threading.Timer(PAUSE_AFTER, refresh_block_card, args=(uid, True))
        t.daemon = True
        _pause[uid] = t
        t.start()


def open_block(uid, b):
    """
    Картка надсилається і закріплюється рівно один раз на блок, далі тільки
    редагується. Одне сповіщення на блок, нуль на файл.
    """
    store.set_active_block(uid, b["id"])
    _asked_block.pop(uid, None)
    m = api("sendMessage", chat_id=uid, text=block_card_text(b),
            reply_markup=block_card_kb(), disable_web_page_preview=True)
    if m:
        mid = m.get("message_id")
        store.set_user(uid, block_msg=mid)
        api("unpinAllChatMessages", chat_id=uid)
        api("pinChatMessage", chat_id=uid, message_id=mid, disable_notification=True)
    touch_pause(uid)


def show_block_menu(uid, message_id=None):
    kb = kinds_kb()
    if not kb:
        send(uid, "Список блоків ще порожній, скажи Yaro ♥️")
        return
    text = "Над чим зараз працюємо?"
    if message_id and api("editMessageText", chat_id=uid, message_id=message_id,
                          text=text, reply_markup=kb):
        return
    send(uid, text, kb)


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
            send(a["chat_id"], "Прийняла всі " + str(a["n"]) + " ♥️ Передаю Yaro.")
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
    b = store.active_block(uid) if reply else None
    target_block = b or (store.inbox_block() if reply else None)
    row = store.add_asset(uid, fid, kind, caption=caption or None,
                          media_group=str(gid) if gid else None, file_unique_id=fuid,
                          block_id=target_block["id"] if target_block else None)
    for cid in NOTIFY_IDS:
        if cid != uid:
            api("forwardMessage", chat_id=cid, from_chat_id=chat_id, message_id=m.get("message_id"))
    if reply:
        # Їй бот не відповідає на кожен файл і нічого в неї не питає:
        # мовчки перемальовує одну картку. Меню вона відкриє сама, якщо схоче.
        touch_pause(uid)
        ensure_card(uid, b)
        src = "Від Іри · " + block_name(b) if b else "Від Іри · без блоку"
    if gid:
        album_touch(str(gid), chat_id, kind, caption, src=src, reply=False)
        return
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
    store.session_begin()
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
                me = store.touch_user(u, role="admin" if uid == ADMIN_ID else "ira") or {}
                # Режим Іри: Yaro бачить бота рівно так, як бачитиме вона.
                # Потрібен, щоб перевіряти її досвід до того, як вона його отримає.
                as_ira = uid == ADMIN_ID and bool(me.get("as_ira"))
                if uid == ADMIN_ID and text.split(" ")[0] in ("/ira", "/яідр"):
                    store.set_user(uid, as_ira=not as_ira)
                    if as_ira:
                        send(chat_id, "Вийшов з режиму Іри.", admin_kb())
                    else:
                        send(chat_id, "Режим Іри. Бачиш і поводишся як вона. "
                                      "Назад: /ira", IRA_KB)
                    return "ok"
                if as_ira:
                    name = "Іра"
                    low = text.lower()
                    if low in ("мої задачі", "мои задачи"):
                        show_tasks(uid, name)
                        return "ok"
                    if low in ("матеріали", "материалы"):
                        show_block_menu(uid)
                        return "ok"
                    if low in ("додати", "добавить"):
                        send(chat_id, "Напишіть задачу з плюсом попереду, наприклад: +купити фон")
                        return "ok"
                    if text and not extract_file(m)[1]:
                        b = store.find_block(text)
                        if b:
                            open_block(uid, b)
                            return "ok"
                        if re.search(r"схем\w*\s*[№#]?\s*\d{1,2}", text, re.I) and len(text) <= 60:
                            send(chat_id, "Такої схеми не бачу, напиши назву ♥️")
                            return "ok"
                    take_material(m, chat_id, uid)
                    return "ok"
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
                if uid == ADMIN_ID and text.startswith("/blocks"):
                    rows = store.blocks_with_material() or []
                    if not rows:
                        send(chat_id, "Матеріалів по блоках ще немає.")
                    else:
                        out = ["Блоки з матеріалом:"]
                        for r in rows:
                            nm = ("Схема " + str(r["code"]) + " · " + r["title"]) \
                                 if r["kind"] == "schema" and r["code"] else r["title"]
                            out.append("· " + nm + " — " + str(r["n"]))
                        act = store.active_block(IRA_ID) if IRA_ID else None
                        out.append("\nЗараз у роботі: " + (block_name(act) if act else "нічого"))
                        send(chat_id, "\n".join(out))
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
                    if low in ("матеріали", "материалы"):
                        show_block_menu(uid)
                        return "ok"
                    if low in ("додати", "добавить"):
                        send(chat_id, "Напишіть задачу з плюсом попереду, наприклад: +купити фон")
                        return "ok"
                    # Заголовок текстом швидший за два тапи, коли вона в потоці.
                    # Помилка тут дешева: картка одразу покаже назву не того блоку.
                    if text and not extract_file(m)[1]:
                        b = store.find_block(text)
                        if b:
                            open_block(uid, b)
                            return "ok"
                        if re.match(r"^\s*схем[аиу]\s*[№#]?\s*\d{1,2}\s*\.?\s*$", text, re.I):
                            send(chat_id, "Такої схеми не бачу, напиши назву ♥️")
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
                send(chat_id, "Прийняла ♥️ Якщо це про зйомку, напишіть в інстаграм, "
                              "там відповідаю швидше: @iryna_rul_photographer")
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            api("answerCallbackQuery", callback_query_id=cq["id"])
            data = cq.get("data") or ""
            chat_id = cq["message"]["chat"]["id"]
            u = cq.get("from", {})
            uid = u.get("id")
            if data[:2] in ("bk", "bs", "bd", "bm", "bg") and uid in TEAM and team_on(uid):
                mid = cq["message"].get("message_id")
                if data == "bmenu":
                    show_block_menu(uid, mid)
                    return "ok"
                if data == "bgo":
                    touch_pause(uid)
                    refresh_block_card(uid)
                    return "ok"
                if data == "bdone":
                    store.set_active_block(uid, None)
                    api("editMessageReplyMarkup", chat_id=uid, message_id=mid, reply_markup=None)
                    show_block_menu(uid)
                    return "ok"
                if data.startswith("bk:"):
                    api("editMessageText", chat_id=uid, message_id=mid,
                        text="Що саме?", reply_markup=blocks_kb(data.split(":")[1]))
                    return "ok"
                if data.startswith("bs:"):
                    b = store.get_block(int(data.split(":")[1]))
                    if b:
                        api("deleteMessage", chat_id=uid, message_id=mid)
                        open_block(uid, b)
                    return "ok"
                return "ok"
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
                    body += "\n\nРеквізити надішлю сюди найближчим часом ♥️ Заявку вже бачу, нікуди не зникайте."
                send(chat_id, body, pay_kb(data))
                nudge_later(uid, data, code)
                notify("ЗАЯВКА: " + t["name"] + ", " + str(t["uah"]) + " грн\n"
                       + who(u) + "\nКод: " + code, give_kb(uid, data))
            elif data.startswith("noget:"):
                tier = data.split(":")[1]
                code = order_code(uid, tier)
                send(chat_id, NOGET_TEXT)
                store.log_event(uid, "noget", {"tier": tier, "code": code})
                notify("КАЖЕ, ЩО ОПЛАТИВ, А ФАЙЛУ НЕМАЄ\n"
                       + TIERS.get(tier, {}).get("name", tier) + "\n"
                       + who(u) + "\nКод: " + code, give_kb(uid, tier))
            elif data.startswith("paid:") and TEST_MODE:
                tier = data.split(":")[1]
                code = order_code(uid, tier)
                ok = give_guide(uid, tier)
                if not ok:
                    # Службовий рядок в обличчя людині це теж глухий кут.
                    send(chat_id, BROKEN_FILE_TEXT)
                    notify("ФАЙЛ НЕ ВИДАВСЯ, GUIDE_FILE_ID не заданий або битий\n"
                           + who(u) + "\nКод: " + code, give_kb(uid, tier))
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
    finally:
        store.session_end()
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
        # Людину тут не впізнати, тому Yaro потрібні всі зачіпки одразу:
        # хто відправник, скільки і коли. По імені він упізнає заявку.
        when = tx.get("time")
        when = (time.strftime("%d.%m %H:%M", time.localtime(when)) if when else "час невідомий")
        notify("Оплата " + str(amount // 100) + " грн у банці, але БЕЗ КОДУ.\n"
               "Коли: " + when + "\n"
               "Від кого: " + (tx.get("description") or "не вказано") + "\n"
               "Коментар: " + (tx.get("comment") or "порожній") + "\n\n"
               "Впізнай по імені і видай гайд вручну з відповідної заявки.")
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


KEEPALIVE = {"last_ok": None, "fails": 0}


def keepalive():
    while True:
        time.sleep(600)
        try:
            r = requests.get(BASE_URL + "/", timeout=15)
            if r.status_code == 200:
                KEEPALIVE["last_ok"] = time.time()
                KEEPALIVE["fails"] = 0
            else:
                KEEPALIVE["fails"] += 1
        except Exception:
            KEEPALIVE["fails"] += 1


if BASE_URL:
    threading.Thread(target=keepalive, daemon=True).start()
threading.Thread(target=mono_poll, daemon=True).start()
threading.Thread(target=sync_commands, daemon=True).start()
threading.Thread(target=seed_catalog, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
