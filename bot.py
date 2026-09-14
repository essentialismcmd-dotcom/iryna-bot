#!/usr/bin/env python3
"""
Бот Iryna Rul. Три речі й нічого більше.

1. Лійка: магніт, три пакети гайду, два курси ретуші, оплата в банку Monobank,
   видача файлів.
2. Приймання матеріалів від Іри: вона кидає що завгодно з коротким підписом,
   рівно як кидала в особистий чат. Бот приймає і мовчить.
3. База: усе прийняте лежить у Postgres, звідти це дістає Yaro або Клод.

Чого тут свідомо немає: задачника, блоків, меню, кнопок розкладання,
режимів і клавіатур. Вони були, ними ніхто не користувався, 28.08 вирізані.
Правило: у боті лишається те, що працює само, а не те, що вимагає навчання.
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
# Курс ретуші. Файли великі (відео), тому не URL, а file_id з цього ж бота:
# Yaro пересилає файл боту, бот кладе його в базу (таблиця assets, кошик
# «kurs») і відповідає рядком «kind:file_id». Список для змінної збирається
# з /inbox/<SECRET>. Порядок у змінній це порядок видачі.
COURSE1_FILES = os.getenv("COURSE1_FILES", "").strip()
COURSE2_FILES = os.getenv("COURSE2_FILES", "").strip()
# Ціни в гривнях. Курси: перший, другий, обидва. Без змінних беруться з коду,
# і код тримає таблицю з projects/iryna/TSINY-2026-09-14.md.
COURSE_PRICES = os.getenv("COURSE_PRICES", "").strip()
GUIDE_PRICE   = os.getenv("GUIDE_PRICE", "").strip()
# Які тарифи гайда показувати. t2 і t3 продають час Іри на розбір кадрів,
# а з нею це не домовлено, тому за замовчуванням тільки сам гайд.
GUIDE_TIERS   = [t for t in os.getenv("GUIDE_TIERS", "t1").replace(" ", "").split(",") if t]
TEST_MODE     = os.getenv("TEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
IRA_ON        = os.getenv("IRA_ON", "").strip().lower() in ("1", "true", "yes", "on")
SECRET        = os.getenv("WEBHOOK_SECRET", "hook")
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
    "Хочете всі схеми, а не три, тисніть другу кнопку.\n"
    "Хочете навчитись ретушувати самі, третю."
)
GUIDE_INTRO = (
    "Повний гайд «Світло» ♥️\n\n"
    "Усі мої робочі схеми, від чистої комерції до кольору.\n"
    "Кожна з розстановкою, налаштуваннями і кадром зі зйомки.\n\n"
    "Три варіанти, оберіть свій."
)
NOGET_TEXT = ("Перевірю вручну, зазвичай це кілька хвилин ♥️ "
              "Файл прийде сюди, нічого робити не треба.")

# Курс ретуші. Скрипт з її переписок, де оплата приходила за пʼять хвилин:
# питання-кваліфікатор, рекомендація конкретного курсу, реквізити.
RETUSH_INTRO = (
    "Курс ретуші ♥️\n\n"
    "Два записані курси: з нуля до чистого бʼюті-портрета і окремо ростовий "
    "портрет з фешн-корекцією кольору.\n\n"
    "Щоб порадити свій, одне питання: ви вже знайомі з фотошопом чи тільки починаєте?"
)
RETUSH_NEW = (
    "Тоді вам перший курс ♥️\n\n"
    "Починаємо з основ фотошопу, три уроки, і далі чотири уроки бʼюті-ретуші "
    "портрета: шкіра, обʼєм, колір, чистий кадр без «пластику». "
    "Папка знімків для практики додається.\n\n"
    "Якщо хочете одразу і ростовий портрет, беріть обидва, так дешевше."
)
RETUSH_PRO = (
    "Тоді вам другий курс ♥️\n\n"
    "Сорок хвилин розбору ретуші ростового портрета плюс фешн-корекція кольору: "
    "як я доводжу кадр до журнального вигляду.\n\n"
    "Якщо основи хочеться освіжити, беріть обидва, так дешевше."
)
COURSE_DELIVERED = (
    "Це весь курс, доступ залишається назавжди ♥️\n\n"
    "Як користуватись: спершу відео уроку, потім відкриваєте практику до нього "
    "у Photoshop і повторюєте за мною на тих самих кадрах. Файли можна зберегти "
    "з чату на компʼютер.\n\n"
    "Питання по уроках пишіть прямо сюди, відповідаю."
)
LESSON_DONE = ("Це весь урок ♥️ Відео можна дивитись прямо тут, практику відкривайте "
               "у Photoshop через Camera Raw і повторюйте за мною. Питання пишіть сюди.")
MOI_TEXT = "Ваші матеріали ♥️ Тисніть, і надішлю ще раз."
MOI_EMPTY = ("Поки нічого не куплено ♥️ Безкоштовні три схеми світла по кнопці нижче, "
             "гайд і курс ретуші там само.")
NEXT_AFTER_GUIDE = (
    "І ще одне ♥️ Світло поставили, далі кадр треба довести в ретуші.\n"
    "У мене два записані курси, підберу під ваш рівень."
)
BROKEN_FILE_TEXT = ("Щось пішло не так з файлом ♥️ "
                    "Уже розбираюсь, надішлю сюди за кілька хвилин.")
CLIENT_TEXT = ("Прийняла ♥️ Якщо це про зйомку, напишіть в інстаграм, "
               "там відповідаю швидше: @iryna_rul_photographer")

IRA_HELLO = (
    "Привіт ♥️\n"
    "Кидай сюди все по роботі так само, як кидала мені в чат: правки, фото, "
    "рендери, голосові.\n"
    "Коротко підпиши, для чого це, і все. Розбирати нічого не треба."
)

def _price(raw, default):
    try:
        p = int(raw)
        return p if p > 0 else default
    except ValueError:
        return default


# Ціна гайда: 20 $ його словом 13.09, за курсом 44.6 це 890, округлено до 900.
_G = _price(GUIDE_PRICE, 900)

TIERS = {
    "t1": {"name": "Гайд «Світло»", "uah": _G, "btn": "Гайд, " + str(_G) + " грн",
           "text": ("Гайд «Світло», " + str(_G) + " грн\n\n"
                    "42 сторінки, тринадцять моїх робочих схем: розстановка, "
                    "налаштування і кадр зі зйомки до кожної. Доступ залишається назавжди."),
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


def _prices(raw, default):
    try:
        p = [int(x) for x in raw.replace(" ", "").split(",")]
        return p if len(p) == 3 and all(x > 0 for x in p) else default
    except ValueError:
        return default


# Сходинка лійки: гайд 900 → обидва курси 4 500 (≈100 $, його орієнтир),
# перший окремо 3 200, другий 1 900. Історичні 1800/1300/2700 повертаються
# змінною COURSE_PRICES без деплою. Таблиця з поясненням у коворку,
# projects/iryna/TSINY-2026-09-14.md.
_K1, _K2, _K12 = _prices(COURSE_PRICES, [3200, 1900, 4500])

COURSES = {
    "k1": {"name": "Курс ретуші 1: основи і бʼюті-портрет", "uah": _K1,
           "btn": "Перший курс, " + str(_K1) + " грн",
           "text": ("Курс ретуші 1, " + str(_K1) + " грн\n\n"
                    "Основи фотошопу, три уроки, плюс чотири уроки бʼюті-ретуші портрета "
                    "і папка знімків для практики. Доступ назавжди."),
           "extra": ""},
    "k2": {"name": "Курс ретуші 2: ростовий портрет і колір", "uah": _K2,
           "btn": "Другий курс, " + str(_K2) + " грн",
           "text": ("Курс ретуші 2, " + str(_K2) + " грн\n\n"
                    "Розбір ретуші ростового портрета, сорок хвилин, плюс фешн-корекція "
                    "кольору. Доступ назавжди."),
           "extra": ""},
    "k12": {"name": "Обидва курси ретуші", "uah": _K12,
            "btn": "Обидва курси, " + str(_K12) + " грн",
            "text": ("Обидва курси ретуші, " + str(_K12) + " грн\n\n"
                     "Основи, бʼюті-портрет, ростовий портрет і корекція кольору. "
                     "Усе разом дешевше, ніж окремо. Доступ назавжди."),
            "extra": ""},
}

# Один словник на все, що продається. Цифра після дефіса в коді платежу
# це «code»: 1-3 гайд, 4-6 курси. Старі коди IR...-1 читаються як і раніше.
PRODUCTS = {}
for _k, _v in TIERS.items():
    PRODUCTS[_k] = dict(_v, code=_k[-1], product="guide")
for _k, _c in (("k1", "4"), ("k2", "5"), ("k12", "6")):
    PRODUCTS[_k] = dict(COURSES[_k], code=_c, product="course")
BY_CODE = {v["code"]: k for k, v in PRODUCTS.items()}

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CODE_RE = re.compile(r"IR([0-9A-Z]+)-([1-6])", re.I)


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


def order_code(uid, key):
    return "IR" + b36(uid) + "-" + PRODUCTS.get(key, {}).get("code", key[-1])


def pname(key):
    return PRODUCTS.get(key, {}).get("name", key)


def api_raw(method, **params):
    """Сира відповідь Telegram: {ok, result | description, error_code}."""
    params = {k: v for k, v in params.items() if v is not None}
    try:
        r = requests.post(API + "/" + method, json=params, timeout=20)
        return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def api(method, retry=False, **params):
    """
    retry=True тільки для видачі файлів: на 429 бот чекає стільки, скільки
    просить Telegram, і пробує ще раз. Відповіді в чат так не повторюємо,
    інакше один флуд від адміна заблокує потік вебхука на пів хвилини.
    """
    j = api_raw(method, **params)
    if not j.get("ok") and retry and j.get("error_code") == 429:
        wait = (j.get("parameters") or {}).get("retry_after") or 3
        if wait <= 35:
            time.sleep(wait + 0.5)
            j = api_raw(method, **params)
    if not j.get("ok"):
        log.warning("%s: %s", method, j.get("description"))
    return j.get("result")


def send(chat_id, text, markup=None):
    return api("sendMessage", chat_id=chat_id, text=text,
               reply_markup=markup, disable_web_page_preview=True)


def notify(text, markup=None):
    for cid in NOTIFY_IDS:
        send(cid, text, markup)


def who(u):
    uname = u.get("username")
    tag = "@" + uname if uname else "без юзернейма"
    name = " ".join([x for x in [u.get("first_name"), u.get("last_name")] if x]) or "без імені"
    return name + ", " + tag + ", id " + str(u.get("id"))


# ---------- лійка ----------

def magnet_kb():
    return {"inline_keyboard": [[{"text": "Забрати три схеми світла", "callback_data": "magnet"}]]}


def after_kb():
    rows = []
    if CHANNEL_URL:
        rows.append([{"text": "Канал «для своїх»", "url": CHANNEL_URL}])
    rows.append([{"text": "Хочу повний гайд «Світло»", "callback_data": "guide"}])
    rows.append([{"text": "Курс ретуші", "callback_data": "retush"}])
    return {"inline_keyboard": rows}


def tiers_kb():
    keys = [k for k in ("t1", "t2", "t3") if k in GUIDE_TIERS] or ["t1"]
    return {"inline_keyboard": [[{"text": TIERS[k]["btn"], "callback_data": k}]
                                for k in keys]}


def retush_kb():
    return {"inline_keyboard": [
        [{"text": "Тільки починаю", "callback_data": "q:new"}],
        [{"text": "Вже працюю у фотошопі", "callback_data": "q:pro"}],
    ]}


def course_kb(first):
    """Рекомендований курс першою кнопкою, «обидва» завжди другою."""
    return {"inline_keyboard": [[{"text": COURSES[first]["btn"], "callback_data": first}],
                                [{"text": COURSES["k12"]["btn"], "callback_data": "k12"}]]}


def retush_kb_one():
    return {"inline_keyboard": [[{"text": "Курс ретуші", "callback_data": "retush"}]]}


def pay_kb(key, uid=None):
    rows = []
    if PAY_URL:
        rows.append([{"text": "Перейти до оплати", "url": PAY_URL}])
    # Тестова кнопка тільки адмінам: до 14.09 вона стояла всім, і будь-хто
    # міг забрати гайд безкоштовно, поки TEST_MODE увімкнений на проді.
    if TEST_MODE and uid in NOTIFY_IDS:
        rows.append([{"text": "Я оплатив (тест)", "callback_data": "paid:" + key}])
    # Найдорожчий глухий кут лійки: людина заплатила, а файл не прийшов.
    rows.append([{"text": "Оплатив, а файлу немає", "callback_data": "noget:" + key}])
    return {"inline_keyboard": rows}


def give_kb(uid, key):
    return {"inline_keyboard": [[{"text": "Видати вручну",
                                  "callback_data": "give:" + str(uid) + ":" + key}]]}


def give_magnet(chat_id):
    if not MAGNET_URL:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ♥️")
        return
    if not api("sendDocument", chat_id=chat_id, document=MAGNET_URL):
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ♥️")
        return
    send(chat_id, AFTER, after_kb())


def give_guide(uid, tier):
    if not GUIDE_FILE_ID:
        return False
    if not api("sendDocument", chat_id=uid, document=GUIDE_FILE_ID):
        return False
    extra = TIERS.get(tier, {}).get("extra")
    if extra:
        send(uid, extra)
    # Покупець у момент оплати найтепліший, другого такого моменту не буде.
    send(uid, NEXT_AFTER_GUIDE, retush_kb_one())
    return True


# Telegram не дає змінити тип файлу при повторній відправці за file_id:
# відео, залите як відео, треба слати sendVideo, а не sendDocument.
SEND_BY_KIND = {
    "document": "sendDocument", "video": "sendVideo", "audio": "sendAudio",
    "photo": "sendPhoto", "voice": "sendVoice", "animation": "sendAnimation",
    "video_note": "sendVideoNote",
}
KIND_UA = {"фото": "photo", "відео": "video", "документ": "document",
           "голосове": "voice", "аудіо": "audio", "кружечок": "video_note",
           "гіфка": "animation"}


def parse_files(raw):
    """«video:BAAC...,document:BQAC...» → [(kind, file_id)]. Без kind це документ."""
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        kind, _, fid = part.rpartition(":")
        kind = kind.strip().lower() or "document"
        if kind not in SEND_BY_KIND:
            kind = "document"
        if fid.strip():
            out.append((kind, fid.strip()))
    return out


PRACTICE_CAPTION = ("Практика до уроку: RAW з камери (.raf), мої налаштування Camera Raw "
                    "(.xmp, .acr) і готовий PSD. Відкривайте у Photoshop через Camera Raw "
                    "і повторюйте крок за кроком.")


def parse_course(raw):
    """
    Курс це список розділів: «Урок 1 · основи > video:..,document:.. | Урок 2 > ..».
    Розділи через «|», заголовок від файлів через «>». Без заголовків і без
    «|» це старий плоский формат, він читається як один розділ без назви.
    """
    out = []
    for part in raw.split("|"):
        part = part.strip()
        if not part:
            continue
        title, sep, files = part.partition(">")
        if not sep:
            title, files = "", part
        items = parse_files(files)
        if items:
            out.append((title.strip(), items))
    return out


COURSE_SECTIONS = {"k1": parse_course(COURSE1_FILES), "k2": parse_course(COURSE2_FILES)}
COURSE_SECTIONS["k12"] = COURSE_SECTIONS["k1"] + COURSE_SECTIONS["k2"]
COURSE_FILES = {k: [f for _, fs in v for f in fs] for k, v in COURSE_SECTIONS.items()}


def _send_album(uid, kind, items, caption):
    """Документи або фото одним альбомом (2–10 штук). Повертає скільки пішло."""
    media = [{"type": kind, "media": fid} for fid in items]
    media[0]["caption"] = caption
    if api("sendMediaGroup", retry=True, chat_id=uid, media=media):
        return len(items)
    # Альбом не пройшов (наприклад, різні типи всередині): віддаємо по одному.
    n = 0
    for fid in items:
        time.sleep(1.0)
        if api(SEND_BY_KIND[kind], retry=True, **{"chat_id": uid, kind: fid}):
            n += 1
    return n


def owned_keys(uid):
    """Що людина купила: ключі продуктів з оплачених покупок. Адмін бачить усе."""
    if uid in NOTIFY_IDS:
        return {"t1", "k1", "k2"}
    out = set()
    for p in (store.purchases_of(uid) or []):
        t = p.get("tier") or ""
        if t in ("t1", "t2", "t3"):
            out.add("t1")
        elif t == "k12":
            out.update({"k1", "k2"})
        elif t in ("k1", "k2"):
            out.add(t)
    return out


def lessons_kb(uid, current=None):
    """Кнопки всіх куплених уроків. current це (ключ, номер), його не показуємо."""
    rows = []
    owned = owned_keys(uid)
    if "t1" in owned and GUIDE_FILE_ID:
        rows.append([{"text": "Гайд «Світло»", "callback_data": "my:guide"}])
    for ckey in ("k1", "k2"):
        if ckey not in owned:
            continue
        for i, (title, _files) in enumerate(COURSE_SECTIONS.get(ckey) or []):
            if (ckey, i) == current:
                continue
            rows.append([{"text": title or ("Урок " + str(i + 1)), "callback_data": "les:" + ckey + ":" + str(i)}])
    return {"inline_keyboard": rows} if rows else None


def next_kb(ckey, idx):
    """Після уроку: одна кнопка «Далі» і одна «Усі матеріали»."""
    rows = []
    sections = COURSE_SECTIONS.get(ckey) or []
    if idx + 1 < len(sections):
        nt = sections[idx + 1][0] or ("Урок " + str(idx + 2))
        rows.append([{"text": "Далі: " + nt, "callback_data": "les:" + ckey + ":" + str(idx + 1)}])
    elif ckey == "k1" and COURSE_SECTIONS.get("k2"):
        rows.append([{"text": "Далі: курс 2, колір", "callback_data": "les:k2:0"}])
    rows.append([{"text": "Усі мої матеріали", "callback_data": "moi"}])
    return {"inline_keyboard": rows}


def send_video_or_file(uid, kind, fid, caption):
    """
    Відео має грати в чаті, а не качатись. Якщо файл залитий як документ,
    пробуємо sendVideo, Telegram інколи приймає; якщо ні, віддаємо як є.
    """
    if kind == "video":
        return bool(api("sendVideo", retry=True, chat_id=uid, video=fid, caption=caption, supports_streaming=True))
    if api_raw("sendVideo", chat_id=uid, video=fid, caption=caption, supports_streaming=True).get("ok"):
        return True
    return bool(api(SEND_BY_KIND[kind], retry=True, **{"chat_id": uid, kind: fid, "caption": caption}))


def send_lesson(uid, ckey, idx):
    """Один урок: заголовок, відео, практика альбомом, кнопка «Далі»."""
    sections = COURSE_SECTIONS.get(ckey) or []
    if idx < 0 or idx >= len(sections):
        return False
    title, files = sections[idx]
    total = len(files)
    sent = 0
    if title:
        send(uid, title)
        time.sleep(1.0)
    docs = []
    for kind, fid in files:
        if kind in ("video", "animation", "video_note") or fid.startswith("BAAC") or kind == "document" and _looks_video(ckey, idx, fid):
            if send_video_or_file(uid, kind, fid, title or None):
                sent += 1
            time.sleep(1.0)
        else:
            docs.append((kind, fid))
    for kind in ("document", "photo", "audio", "voice"):
        items = [fid for k, fid in docs if k == kind]
        for i in range(0, len(items), 10):
            chunk = items[i:i + 10]
            if i:
                time.sleep(1.0)
            if len(chunk) == 1:
                cap = PRACTICE_CAPTION if kind == "document" else None
                if api(SEND_BY_KIND[kind], retry=True, **{"chat_id": uid, kind: chunk[0], "caption": cap}):
                    sent += 1
            else:
                sent += _send_album(uid, kind, chunk, PRACTICE_CAPTION if kind == "document" else "")
    if sent < total:
        log.warning("урок %s/%s для %s: пішло %s з %s", ckey, idx, uid, sent, total)
        notify("Урок " + ckey + " №" + str(idx + 1) + " для id " + str(uid) + ": пішло "
               + str(sent) + " з " + str(total) + " файлів.")
    time.sleep(1.0)
    send(uid, LESSON_DONE, next_kb(ckey, idx))
    store.log_event(uid, "lesson", {"course": ckey, "n": idx + 1, "sent": sent, "of": total})
    return sent > 0


def _looks_video(ckey, idx, fid):
    """Перший файл розділу з «Відео» у назві це відео, навіть якщо залите документом."""
    title = (COURSE_SECTIONS.get(ckey) or [("", [])])[idx][0].lower()
    return title.startswith("відео")


def give_course(uid, key):
    """
    Видача не купою, а за руку: інтро зі списком уроків, перший урок одразу,
    решта по кнопці «Далі». Yaro 14.09: «щоб навіть малій дитині було
    зрозуміло», «купа повідомлень, усе загубилось».
    """
    keys = ["k1", "k2"] if key == "k12" else [key]
    if not any(COURSE_SECTIONS.get(k) for k in keys):
        return False
    lines = ["Готово, курс ваш ♥️", ""]
    for k in keys:
        lines.append(COURSES[k]["name"] + ":")
        for i, (title, files) in enumerate(COURSE_SECTIONS.get(k) or []):
            lines.append("  " + str(i + 1) + ". " + (title or "Урок " + str(i + 1)))
        lines.append("")
    lines.append("Йдемо по одному уроку: дивитесь відео, робите практику, тиснете «Далі». "
                 "Усе куплене завжди під рукою в меню «Мої матеріали».")
    send(uid, "\n".join(lines))
    time.sleep(1.0)
    first = next(k for k in keys if COURSE_SECTIONS.get(k))
    return send_lesson(uid, first, 0)


def deliver(uid, key):
    """Видача будь-якого купленого продукту за його ключем."""
    if key in COURSES:
        return give_course(uid, key)
    return give_guide(uid, key)


def ready_text(key):
    if key in COURSES:
        n = len(COURSE_FILES.get(key) or [])
        m = len(COURSE_SECTIONS.get(key) or [])
        return ("у курсі " + str(n) + " файлів у " + str(m) + " розділах") if n else "COURSE1_FILES/COURSE2_FILES не задані"
    return "на місці" if GUIDE_FILE_ID else "GUIDE_FILE_ID не заданий"


# ---------- матеріали від Іри ----------
#
# Вона кидає що завгодно з коротким підписом, рівно як кидала в особистий чат.
# Жодних меню, кнопок і категорій: розбирає це потім Yaro або Клод з бази.

FILE_KINDS = (
    ("photo", "фото"), ("video", "відео"), ("document", "документ"),
    ("voice", "голосове"), ("audio", "аудіо"), ("video_note", "кружечок"),
    ("animation", "гіфка"), ("sticker", "стікер"),
)


def extract_file(m):
    for key, label in FILE_KINDS:
        v = m.get(key)
        if not v:
            continue
        if key == "photo":
            v = v[-1]
        return label, v.get("file_id"), v.get("file_unique_id")
    return None, None, None


_seen_albums = {}
_albums_lock = threading.Lock()


def take_material(m, chat_id, uid):
    kind, fid, fuid = extract_file(m)
    caption = (m.get("caption") or m.get("text") or "").strip()
    gid = m.get("media_group_id")
    if not fid:
        kind, fid, fuid = "текст", "", None
    store.add_asset(uid, fid, kind, caption=caption or None,
                    media_group=str(gid) if gid else None, file_unique_id=fuid)
    for cid in NOTIFY_IDS:
        if cid != uid:
            api("forwardMessage", chat_id=cid, from_chat_id=chat_id,
                message_id=m.get("message_id"))
    # Альбом дає окремий апдейт на кожне фото. Відповідаємо один раз на альбом,
    # інакше на двадцять фото прилетить двадцять «прийняла».
    if gid:
        with _albums_lock:
            first = str(gid) not in _seen_albums
            _seen_albums[str(gid)] = time.time()
            if len(_seen_albums) > 200:
                for k, _ in sorted(_seen_albums.items(), key=lambda x: x[1])[:100]:
                    _seen_albums.pop(k, None)
        if not first:
            return
    send(chat_id, "Прийняла ♥️")


# ---------- оплати ----------

def handle_tx(tx):
    amount = tx.get("amount", 0)
    comment = (tx.get("comment") or "") + " " + (tx.get("description") or "")
    m = CODE_RE.search(comment.replace(" ", ""))
    if not m:
        when = tx.get("time")
        when = time.strftime("%d.%m %H:%M", time.localtime(when)) if when else "час невідомий"
        notify("Оплата " + str(amount // 100) + " грн у банці, але БЕЗ КОДУ.\n"
               "Коли: " + when + "\n"
               "Від кого: " + (tx.get("description") or "не вказано") + "\n"
               "Коментар: " + (tx.get("comment") or "порожній") + "\n\n"
               "Впізнай по імені і видай вручну.")
        return
    try:
        uid = unb36(m.group(1).upper())
    except Exception:
        return
    key = BY_CODE.get(m.group(2), "t" + m.group(2))
    code = "IR" + m.group(1).upper() + "-" + m.group(2)
    need = PRODUCTS.get(key, {}).get("uah", 0) * 100
    if amount < need * 0.9:
        store.log_event(uid, "pay_short", {"code": code, "uah": amount // 100})
        notify("Оплата " + str(amount // 100) + " грн за кодом " + code
               + ", а треба " + str(need // 100) + " грн. " + pname(key) + ": не видано.")
        return
    store.mark_paid(code, amount // 100)
    ok = deliver(uid, key)
    if ok:
        store.mark_delivered(code)
    store.log_event(uid, "pay_ok" if ok else "pay_undelivered", {"code": code})
    if ok:
        notify("Оплата " + str(amount // 100) + " грн, код " + code + ". "
               + pname(key) + ": видано автоматично.")
    else:
        notify("Оплата " + str(amount // 100) + " грн, код " + code
               + ", але файл не пішов. " + pname(key) + ": " + ready_text(key),
               give_kb(uid, key))


def mono_poll():
    """
    Виписка читається щохвилини з чимось, а в базу ходимо тільки за новою
    транзакцією. seen це фільтр першого рівня, mono_tx у базі другого:
    він переживає рестарт і не дає видати гайд двічі.
    """
    seen = set()
    ever = None
    first = True
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


# ---------- службове, у меню команд не виводиться ----------

def status_text():
    d = store.stats_day() if store.ON else None
    if not store.ON:
        db = "вимкнена, DATABASE_URL не заданий"
    elif not d or not d.get("now"):
        db = "НЕ ВІДПОВІДАЄ"
    else:
        db = "жива"
    lines = [
        "База: " + db,
        "Комміт: " + (os.getenv("RENDER_GIT_COMMIT", "")[:7] or "невідомий"),
        "Тестовий режим: " + ("увімкнений, кнопка тільки адмінам" if TEST_MODE else "вимкнений"),
        "Банка: " + ("підключена" if PAY_URL else "не підключена")
        + " · токен Mono: " + ("є" if MONO_TOKEN and MONO_JAR else "немає"),
        "Бот Іри: " + ("увімкнений" if IRA_ON else "вимкнений"),
        "Магніт: " + ("URL заданий" if MAGNET_URL else "MAGNET_URL не заданий")
        + " · канал: " + ("кнопка є" if CHANNEL_URL else "CHANNEL_URL не заданий"),
        "Гайд: " + ready_text("t1") + " · тарифи " + ",".join(GUIDE_TIERS) + " · " + str(_G) + " грн",
        "Курс 1: " + ready_text("k1") + " · курс 2: " + ready_text("k2"),
        "Ціни курсів: " + str(_K1) + " / " + str(_K2) + " / " + str(_K12) + " грн",
    ]
    if d and d.get("now"):
        paid = d.get("paid") or {}
        lines.append("")
        lines.append("За добу: стартів " + str((d.get("starts") or {}).get("n", 0))
                     + " · магніт " + str((d.get("magnet") or {}).get("n", 0))
                     + " · оплат " + str(paid.get("n", 0)) + " на "
                     + str(paid.get("uah", 0)) + " грн")
        lines.append("Матеріалів від Іри: " + str(store.inbox_count()))
    return "\n".join(lines)


def send_file(chat_id, name, blob, caption=None):
    try:
        r = requests.post(API + "/sendDocument",
                          data={"chat_id": chat_id, "caption": caption or ""},
                          files={"document": (name, blob)}, timeout=60)
        j = r.json()
        if not j.get("ok"):
            log.warning("sendDocument: %s", j.get("description"))
        return j.get("result") if j.get("ok") else None
    except Exception as e:
        log.warning("sendDocument: %s", e)
        return None


def mb(size):
    return str(round((size or 0) / 1024 / 1024, 1)) + " МБ"


def admin_file(m):
    """
    Адмін кидає або пересилає будь-який файл. Бот кладе його в базу, кошик
    «kurs», з іменем файлу і підписом, і відповідає рядком для COURSE*_FILES.
    13.09 Yaro переслав ~60 файлів курсу, а стара версія на них відповідала
    «Прийняла» і в базу не клала: file_id пропали. Тому спершу база, потім
    відповідь.
    """
    for key, label in FILE_KINDS:
        v = m.get(key)
        if not v:
            continue
        if key == "sticker":
            return None
        if key == "photo":
            v = v[-1]
        size = v.get("file_size")
        name = v.get("file_name") or ""
        caption = (m.get("caption") or "").strip()
        store.add_asset(m.get("from", {}).get("id"), v.get("file_id"), label, bucket="kurs",
                        caption=caption or None, file_unique_id=v.get("file_unique_id"),
                        media_group=str(m["media_group_id"]) if m.get("media_group_id") else None,
                        file_name=name or None, file_size=size)
        return (key + ":" + v.get("file_id", "?")
                + "\n" + (name or "без імені") + (", " + mb(size) if size else ""))
    return None


def assets_lines(limit=200):
    """Матеріали з бази рядками «kind:file_id», найновіші внизу."""
    rows = store.assets_recent(limit=limit) or []
    out = []
    for r in reversed(rows):
        if not r.get("file_id") and r.get("file_kind") != "текст":
            continue
        kind = KIND_UA.get(r.get("file_kind") or "", r.get("file_kind") or "document")
        # Текст від адміна (тексти схем Іри) віддаємо цілком: він і є матеріал.
        cap = r.get("caption") or ""
        if r.get("file_kind") == "текст":
            out.append("#" + str(r.get("id")) + "  " + str(r.get("created_at"))[:19]
                       + "  " + str(r.get("bucket")) + "  ТЕКСТ\n" + cap + "\n---")
            continue
        out.append("#" + str(r.get("id")) + "  " + str(r.get("created_at"))[:19]
                   + "  " + str(r.get("bucket")) + "  " + (r.get("file_name") or "")
                   + ("  " + mb(r["file_size"]) if r.get("file_size") else "")
                   + ("  «" + cap[:60] + "»" if cap else "")
                   + "\n" + kind + ":" + r["file_id"])
    if not rows:
        return "У базі матеріалів немає або база вимкнена."
    return "\n\n".join(out) or "У базі тільки текст, файлів немає."


def perevirka_lines():
    """
    Чи живі file_id, які бот віддає за гроші. getFile не надсилає нічого
    нікому: він або віддає розмір, або каже «file is too big» (файл є,
    просто понад 20 МБ), або «wrong file_id» (файл зламаний).
    """
    items = [("гайд t1", "document", GUIDE_FILE_ID)]
    for key in ("k1", "k2"):
        for i, (kind, fid) in enumerate(COURSE_FILES.get(key) or []):
            items.append((key + " №" + str(i + 1), kind, fid))
    out = []
    for label, kind, fid in items:
        if not fid:
            out.append(label + ": НЕ ЗАДАНИЙ")
            continue
        j = api_raw("getFile", file_id=fid)
        if j.get("ok"):
            out.append(label + ": є, " + mb((j.get("result") or {}).get("file_size")) + ", " + kind)
        elif "too big" in (j.get("description") or "").lower():
            out.append(label + ": є, понад 20 МБ, " + kind)
        else:
            out.append(label + ": ЗЛАМАНИЙ, " + str(j.get("description")))
    return "\n".join(out)


# ---------- маршрути ----------

@app.get("/")
def health():
    return "ok"


PRYVATNIST = """<!doctype html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Політика конфіденційності</title>
<style>
 body{font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;
      margin:0 auto;padding:32px 20px;color:#1c1e21;background:#fff}
 h1{font-size:26px;margin:0 0 4px} h2{font-size:18px;margin:28px 0 8px}
 .d{color:#65676b;font-size:14px;margin-bottom:24px}
 ul{padding-left:20px} hr{border:0;border-top:1px solid #dadde1;margin:36px 0}
 code{background:#f0f2f5;padding:1px 5px;border-radius:4px}
</style></head><body>

<h1>Політика конфіденційності</h1>
<div class="d">Застосунок <code>iryna-reklama</code> &middot; оновлено 4 вересня 2026</div>

<h2>Хто оператор</h2>
<p>Застосунком керує Ярослав Копчик приватно. Зв'язок:
<a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>.</p>

<h2>Для чого застосунок</h2>
<p>Застосунок обслуговує рекламний кабінет і професійний акаунт Instagram,
якими оператор керує за дорученням власниці акаунта. Публічної реєстрації
користувачів немає, стороннім людям він не доступний.</p>

<h2>Які дані обробляються</h2>
<ul>
 <li>Статистика реклами: витрати, покази, кліки, розмови.</li>
 <li>Повідомлення в Instagram Direct і коментарі акаунта, яким керує оператор,
     разом з іменем співрозмовника, яке видно в самому листуванні.</li>
 <li>Службові ідентифікатори сторінки, акаунта Instagram і рекламного кабінету.</li>
</ul>

<h2>Навіщо</h2>
<p>Щоб відповідати на звернення клієнток цього акаунта і оцінювати
результативність реклами. Інших цілей немає.</p>

<h2>Кому передаються</h2>
<p>Нікому. Дані не продаються, не передаються рекламним мережам і не
використовуються для профілювання за межами цього акаунта.</p>

<h2>Де зберігаються і як довго</h2>
<p>На робочому комп'ютері оператора та на сервері цього застосунку, доки
триває робота з акаунтом. Після припинення роботи дані видаляються.</p>

<h2>Видалення даних</h2>
<p>Напишіть на <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>
з темою <b>Видалення даних</b>. Дані видаляються протягом 30 днів,
підтвердження надсилається у відповідь. Власниця акаунта може будь-коли
відкликати доступ застосунку в налаштуваннях Meta, і обробка припиняється
того ж дня.</p>

<hr>

<h1>Privacy Policy</h1>
<div class="d">App <code>iryna-reklama</code> &middot; updated 4 September 2026</div>

<h2>Operator</h2>
<p>This app is operated privately by Yaroslav Kopchyk.
Contact: <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>.</p>

<h2>Purpose</h2>
<p>The app serves one advertising account and one Instagram professional account
that the operator manages on behalf of the account owner. There is no public
sign-up and no access for third parties.</p>

<h2>Data processed</h2>
<ul>
 <li>Advertising statistics: spend, impressions, clicks, conversations.</li>
 <li>Instagram Direct messages and comments of the managed account, including
     the sender name visible in the conversation itself.</li>
 <li>Technical identifiers of the Page, Instagram account and ad account.</li>
</ul>

<h2>Why</h2>
<p>To answer enquiries from this account's clients and to measure advertising
performance. No other purpose.</p>

<h2>Sharing</h2>
<p>None. Data is not sold, not shared with ad networks, and not used for
profiling beyond this account.</p>

<h2>Storage and retention</h2>
<p>On the operator's working computer and on this app's server, for as long as
the work on the account continues. Data is deleted when the work ends.</p>

<h2>Data deletion</h2>
<p>Email <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>
with the subject <b>Data deletion</b>. Data is deleted within 30 days and a
confirmation is sent in reply. The account owner can revoke the app's access in
Meta settings at any time, which stops processing the same day.</p>

</body></html>"""


@app.get("/privacy")
def privacy():
    """Політика конфіденційності. Meta вимагає публічну адресу для публікації
    застосунку, ця сторінка і є нею. Служить водночас інструкцією з видалення
    даних."""
    return PRYVATNIST, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/setup")
def setup():
    base = request.url_root.rstrip("/")
    r = api("setWebhook", url=base + "/" + SECRET,
            allowed_updates=["message", "callback_query"])
    return "setWebhook: " + str(r)


@app.get("/hookinfo/" + SECRET)
def hookinfo():
    i = api("getWebhookInfo") or {}
    return "<pre>url: %s\nу черзі: %s\nостання помилка: %s</pre>" % (
        i.get("url") or "ПОРОЖНЬО", i.get("pending_update_count", "?"),
        i.get("last_error_message") or "немає")


@app.get("/db/" + SECRET)
def db_status():
    return "<pre>" + status_text() + "</pre>"


@app.get("/inbox/" + SECRET)
def inbox_page():
    """Усі матеріали з бази рядками «kind:file_id»: з них збираються COURSE*_FILES."""
    store.session_begin()
    try:
        return "<pre>" + assets_lines() + "</pre>"
    finally:
        store.session_end()


@app.get("/perevirka/" + SECRET)
def perevirka_page():
    return "<pre>" + perevirka_lines() + "</pre>"


@app.get("/file/" + SECRET + "/<int:aid>")
def file_page(aid):
    """
    Віддає файл з бази сесії на перегляд: getFile і потяг з серверів Telegram.
    Межа Bot API 20 МБ, більше віддає текст помилки. Для рендерів схем і
    кадрів у гайд цього досить, PSD і RAW курсу так не забрати.
    """
    store.session_begin()
    try:
        a = store.get_asset(aid)
    finally:
        store.session_end()
    if not a or not a.get("file_id"):
        return "немає такого запису або він без файлу", 404
    j = api_raw("getFile", file_id=a["file_id"])
    if not j.get("ok"):
        return "getFile: " + str(j.get("description")), 502
    path = (j.get("result") or {}).get("file_path")
    if not path:
        return "getFile без file_path", 502
    try:
        r = requests.get("https://api.telegram.org/file/bot" + TOKEN + "/" + path,
                         timeout=120, stream=True)
    except Exception as e:
        return "потяг: " + str(e), 502
    if r.status_code != 200:
        return "потяг: " + str(r.status_code), 502
    name = a.get("file_name") or os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "pdf": "application/pdf", "txt": "text/plain; charset=utf-8"}.get(ext, "application/octet-stream")
    return r.iter_content(65536), 200, {"Content-Type": ctype,
                                          "Content-Disposition": "inline; filename*=UTF-8''" + requests.utils.quote(name)}


@app.get("/events/" + SECRET)
def events_page():
    """Останні події журналу: текст, який до 14.09 07:3x в assets не потрапляв."""
    store.session_begin()
    try:
        rows = store.events_recent(limit=200) or []
    finally:
        store.session_end()
    out = []
    for r in reversed(rows):
        p = r.get("payload") or {}
        out.append("#" + str(r.get("id")) + "  " + str(r.get("created_at"))[:19] + "  " + str(r.get("user_id")) + "  " + str(r.get("kind"))
                   + "  " + (str(p.get("text") or p)[:300]).replace("\n", " / "))
    return "<pre>" + "\n".join(out) + "</pre>"


@app.post("/zalyvka/" + SECRET)
def zalyvka():
    """
    Заливка файлу в Telegram з боку сесії, без токена в її руках: сесія шле
    файл сюди, бот надсилає його адміну і повертає рядок «kind:file_id».
    Так гайд v9 не лежить у публічному репозиторії. Захищено тим самим
    секретом, що й вебхук, /db і /dm.
    """
    f = request.files.get("file")
    if not f or not ADMIN_ID:
        return "потрібен файл у полі file і ADMIN_ID", 400
    blob = f.read()
    name = f.filename or "file.bin"
    r = send_file(ADMIN_ID, name, blob, "Заливка: " + name + ", " + mb(len(blob)))
    doc = (r or {}).get("document") or {}
    fid = doc.get("file_id")
    if not fid:
        return "не залилось: " + name, 502
    store.session_begin()
    try:
        store.add_asset(ADMIN_ID, fid, "документ", bucket="zalyvka",
                        file_unique_id=doc.get("file_unique_id"),
                        file_name=name, file_size=len(blob))
    finally:
        store.session_end()
    log.info("ЗАЛИВКА %s, %s б, file_id=%s", name, len(blob), fid)
    return "document:" + fid + "\n" + name + ", " + mb(len(blob)) + "\n"


@app.get("/jars/" + SECRET)
def jars():
    if not MONO_TOKEN:
        return "MONO_TOKEN не заданий"
    try:
        r = requests.get(MONO + "/personal/client-info",
                         headers={"X-Token": MONO_TOKEN}, timeout=20)
        if r.status_code != 200:
            return "monobank: " + str(r.status_code)
        out = ["<pre>"]
        for j in (r.json().get("jars") or []):
            out.append(str(j.get("title")) + "  id: " + str(j.get("id")))
        return "\n".join(out) + "</pre>"
    except Exception as e:
        return "помилка: " + str(e)


# --------------------------------------------------------------- дірект
# Приймач повідомлень Instagram. Два джерела одночасно:
#
#   1. Meta напряму, вебхук поля `messages` нашого власного застосунку.
#   2. Сторонній посередник (ManyChat і подібні), якщо ми колись його візьмемо.
#
# 31.08.2026 тут стояв коментар «прямого доступу немає, Advanced Access
# упирається у ФОП». Це не доведено: документація Meta каже, що застосунок,
# який обслуговує ЛИШЕ власний або керований акаунт, обходиться Standard
# Access без App Review і без верифікації бізнесу. Питання відкрите і
# міряється тестом на трьох сторонах, розбір у K-124.
#
# Формат посередника навмисно вільний: поля в різних сервісів звуться
# по-різному. Тому беремо перше, що знайшли, а сире тіло кладемо в payload,
# щоб нічого не втратити при зміні провайдера.

VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "").strip() or SECRET


def _pick(d, *names, default=None):
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return v
    return default


def _rozgornuty_meta(d):
    """Meta шле вкладений конверт entry[].messaging[]. Розкладаємо на плоскі
    записи того ж вигляду, що й від посередника.

    Ключове місце це ЧИЙ ідентифікатор брати за контакт. У ехо (повідомлення
    написала сама Іра) відправник це її акаунт, а співрозмовниця сидить у
    recipient. Візьмемо sender наосліп, і вся переписка ляже в тред «Іра з
    самою собою».
    """
    out = []
    for e in d.get("entry") or []:
        for m in (e.get("messaging") or e.get("standby") or []):
            msg = m.get("message") or {}
            echo = bool(msg.get("is_echo"))
            spivrozmovnyk = (m.get("recipient") or {}) if echo else (m.get("sender") or {})
            out.append({
                "ig_id": spivrozmovnyk.get("id"),
                "text": msg.get("text"),
                "is_echo": echo,
                "mid": msg.get("mid"),
                "kind": "message" if msg.get("text") else "attachment",
                "_syre": m,
            })
    return out


@app.get("/dm-hook/" + SECRET)
def dm_verify():
    """Перевірка вебхука від Meta. Вона шле GET з hub.challenge і чекає його
    назад голим текстом. Окремий шлях, бо GET /dm/<SECRET> віддає сторінку
    стану, і Meta на ній не пройшла б перевірку. Окремий префікс, а не
    підшлях, щоб не сперечатись з правилом /dm/<SECRET>/<кого>."""
    if request.args.get("hub.mode") == "subscribe" and \
       request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "ni", 403


@app.post("/dm-hook/" + SECRET)
def dm_hook_meta():
    """Вебхук Meta. Той самий запис, що й у посередника, інший конверт."""
    d = request.get_json(silent=True) or {}
    zapysy = _rozgornuty_meta(d)
    if not zapysy:
        return {"ok": True, "zapysano": 0}, 200
    n = 0
    store.session_begin()
    try:
        for z in zapysy:
            if not z["ig_id"]:
                continue
            cid = store.dm_contact(z["ig_id"])
            store.dm_event(cid, "out" if z["is_echo"] else "in",
                           body=z["text"], kind=z["kind"],
                           payload=z["_syre"], ext_id=z["mid"])
            n += 1
        return {"ok": True, "zapysano": n}, 200
    except Exception as e:
        log.warning("dm_hook_meta впав: %s", e)
        # Meta повторює доставку на не-200, тому віддаємо 200 і ловимо в лозі.
        return {"ok": False, "err": str(e)[:200]}, 200
    finally:
        store.session_end()


@app.post("/dm/" + SECRET)
def dm_hook():
    d = request.get_json(silent=True) or {}
    store.session_begin()
    try:
        ig_id = _pick(d, "ig_id", "subscriber_id", "sender_id", "user_id", "id")
        if not ig_id:
            return {"ok": False, "err": "немає ідентифікатора"}, 400
        cid = store.dm_contact(
            ig_id,
            username=_pick(d, "username", "ig_username", "user_name"),
            display_name=_pick(d, "name", "full_name", "display_name"),
            lang=_pick(d, "lang", "language"),
        )
        body = _pick(d, "text", "message", "body", "last_input_text")
        # in це від людини, out це від акаунта Іри. Прапорець is_echo у Meta
        # означає, що повідомлення надіслав сам акаунт, зокрема з телефона.
        echo = bool(_pick(d, "is_echo", "echo", default=False))
        direction = _pick(d, "direction")
        if direction not in ("in", "out"):
            direction = "out" if echo else "in"
        store.dm_event(cid, direction, body=body,
                       kind=_pick(d, "kind", default="message"),
                       payload=d, ext_id=_pick(d, "mid", "message_id", "ext_id"))
        return {"ok": True, "contact": cid, "direction": direction}
    except Exception as e:
        log.warning("dm_hook впав: %s", e)
        return {"ok": False, "err": str(e)[:200]}, 500
    finally:
        store.session_end()


@app.get("/dm/" + SECRET)
def dm_stan():
    """Що зараз у діректі. Стан обчислюється з подій, не зберігається полем."""
    store.session_begin()
    try:
        st = store.dm_stats()
        rows = store.dm_state(limit=60)
        out = ["<pre>", "СТАН ДІРЕКТУ"]
        sv = (st.get("svizhist") or {}).get("ostannia")
        out.append("контактів %s, подій %s, остання подія %s" % (
            (st.get("kontaktiv") or {}).get("n", "?"),
            (st.get("podii") or {}).get("n", "?"), sv or "НЕМАЄ"))
        for z in (st.get("zakryttia") or []):
            out.append("  закрив %s: %s" % (z.get("closed_by"), z.get("n")))
        out.append("")
        out.append("%-22s %-7s %5s %5s %8s  %s" % (
            "хто", "останнє", "від", "нам", "годин", "останнє повідомлення"))
        for r in rows:
            out.append("%-22s %-7s %5s %5s %8.1f  %s%s" % (
                (r.get("username") or r.get("display_name") or r.get("ig_id"))[:22],
                r.get("hto_ostannim") or "-",
                r.get("vid_ludyny"), r.get("vid_nas"),
                float(r.get("hodyn_movchannia") or 0),
                "[?] " if r.get("pytannia_bez_vidpovidi") else "",
                (r.get("ostannie") or "")[:60].replace("\n", " ")))
        return "\n".join(out) + "</pre>"
    finally:
        store.session_end()


@app.get("/dm/" + SECRET + "/<kogo>")
def dm_lyudyna(kogo):
    """Уся переписка з конкретною людиною."""
    store.session_begin()
    try:
        c = store.dm_one(kogo)
        if not c:
            return "<pre>не знайдено: " + kogo + "</pre>"
        out = ["<pre>", "%s  @%s  ig:%s  сегмент:%s" % (
            c.get("display_name") or "", c.get("username") or "",
            c.get("ig_id"), c.get("segment") or "-"), ""]
        for m in reversed(store.dm_thread(c["id"], limit=60)):
            out.append("%s %-6s %s" % (
                str(m.get("ts"))[:16],
                "ІРА" if m.get("direction") == "out" else "клієнт",
                (m.get("body") or "[вкладення]")[:150].replace("\n", " ")))
        return "\n".join(out) + "</pre>"
    finally:
        store.session_end()


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

            # Службове для Yaro: у меню команд цього немає навмисно.
            if uid == ADMIN_ID:
                if text.startswith("/status"):
                    send(chat_id, status_text())
                    return "ok"
                if text.startswith("/export"):
                    if store.ON:
                        send_file(chat_id, "iryna-bot-" + time.strftime("%Y-%m-%d") + ".json",
                                  store.export_all(), "Вивантаження бази")
                    else:
                        send(chat_id, "Сховище вимкнене.")
                    return "ok"
                if text.startswith("/inbox"):
                    body = assets_lines(limit=40)
                    for i in range(0, len(body), 3900):
                        send(chat_id, body[i:i + 3900])
                    return "ok"
                if text.startswith("/perevirka"):
                    send(chat_id, perevirka_lines())
                    return "ok"
                if text.startswith("/nova"):
                    # Почати з чистого: далі він видаляє чат і тисне /start як новачок.
                    store.forget_user(uid)
                    send(chat_id, "Чисто. Видали цей чат і зайди в бота заново, побачиш його як нова людина.")
                    return "ok"
                fid_line = admin_file(m)
                if fid_line:
                    send(chat_id, "У базі, кошик kurs:\n" + fid_line)
                    return "ok"
                if text and not text.startswith("/"):
                    # Тексти схем від Іри він теж пересилає. Зберігаємо цілком:
                    # до 14.09 07:3x вони летіли в events обрізаними до 300 знаків.
                    store.add_asset(uid, "", "текст", bucket="kurs", caption=text,
                                    media_group=str(m["media_group_id"]) if m.get("media_group_id") else None)
                    send(chat_id, "У базі, текст: " + text[:40].replace("\n", " ") + ("…" if len(text) > 40 else ""))
                    return "ok"

            # Іра: кидає що завгодно, бот приймає і мовчить.
            if uid == IRA_ID and IRA_ON:
                store.touch_user(u, role="ira")
                if text.startswith("/start"):
                    send(chat_id, IRA_HELLO)
                    return "ok"
                take_material(m, chat_id, uid)
                return "ok"

            if text.startswith("/moi") or text.strip() == "Мої матеріали":
                store.touch_user(u)
                kb = lessons_kb(uid)
                send(chat_id, MOI_TEXT if kb else MOI_EMPTY, kb or magnet_kb())
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
                send(chat_id, CLIENT_TEXT)
            return "ok"

        if "callback_query" in upd:
            cq = upd["callback_query"]
            data = cq.get("data") or ""
            u = cq.get("from", {})
            uid = u.get("id")
            chat_id = cq["message"]["chat"]["id"]
            api("answerCallbackQuery", callback_query_id=cq["id"])

            if data == "magnet":
                give_magnet(chat_id)
                store.mark_magnet(uid)
                store.log_event(uid, "magnet")
            elif data == "guide":
                store.log_event(uid, "guide_open")
                send(chat_id, GUIDE_INTRO, tiers_kb())
            elif data == "retush":
                store.log_event(uid, "retush_open")
                send(chat_id, RETUSH_INTRO, retush_kb())
            elif data in ("q:new", "q:pro"):
                # Кваліфікатор з її скрипту: новачкам перший курс, решті другий.
                store.log_event(uid, "retush_level", {"level": data[2:]})
                if data == "q:new":
                    send(chat_id, RETUSH_NEW, course_kb("k1"))
                else:
                    send(chat_id, RETUSH_PRO, course_kb("k2"))
            elif data in PRODUCTS:
                t = PRODUCTS[data]
                code = order_code(uid, data)
                store.add_purchase(uid, t["product"], tier=data, order_code=code,
                                   amount_uah=t["uah"])
                store.log_event(uid, "tier_pick", {"tier": data, "code": code})
                body = t["text"] + "\n\nПризначення платежу, впишіть його дослівно:\n" + code
                if PAY_URL:
                    body += ("\n\nФайли прийдуть сюди самі, зазвичай за хвилину після оплати."
                             if data in COURSES else
                             "\n\nФайл прийде сюди сам, зазвичай за хвилину після оплати.")
                else:
                    body += "\n\nРеквізити надішлю сюди найближчим часом ♥️ Заявку вже бачу."
                send(chat_id, body, pay_kb(data, uid))
                notify("ЗАЯВКА: " + t["name"] + "\n" + who(u) + "\nКод: " + code,
                       give_kb(uid, data))
            elif data.startswith("noget:"):
                key = data.split(":")[1]
                code = order_code(uid, key)
                send(chat_id, NOGET_TEXT)
                store.log_event(uid, "noget", {"code": code})
                notify("КАЖЕ, ЩО ОПЛАТИВ, А ФАЙЛУ НЕМАЄ\n" + pname(key) + "\n" + who(u)
                       + "\nКод: " + code, give_kb(uid, key))
            elif data.startswith("paid:") and TEST_MODE and uid in NOTIFY_IDS:
                key = data.split(":")[1]
                code = order_code(uid, key)
                ok = deliver(uid, key)
                if not ok:
                    send(chat_id, BROKEN_FILE_TEXT)
                    notify("ФАЙЛ НЕ ВИДАВСЯ. " + pname(key) + ": " + ready_text(key)
                           + "\n" + who(u))
                store.mark_paid(code)
                if ok:
                    store.mark_delivered(code)
                store.log_event(uid, "pay_test", {"tier": key, "ok": ok})
                notify("ТЕСТ оплати: " + pname(key) + "\n" + who(u))
            elif data == "moi":
                kb = lessons_kb(uid)
                send(chat_id, MOI_TEXT if kb else MOI_EMPTY, kb or magnet_kb())
            elif data == "my:guide":
                if "t1" in owned_keys(uid) and GUIDE_FILE_ID:
                    api("sendDocument", chat_id=chat_id, document=GUIDE_FILE_ID)
                else:
                    send(chat_id, MOI_EMPTY, magnet_kb())
            elif data.startswith("les:"):
                _, ckey, n = (data.split(":") + ["", ""])[:3]
                if ckey in owned_keys(uid):
                    send_lesson(chat_id, ckey, int(n or 0))
                else:
                    send(chat_id, MOI_EMPTY, magnet_kb())
            elif data.startswith("give:") and uid in NOTIFY_IDS:
                parts = (data.split(":") + ["", ""])[:3]
                target = int(parts[1])
                key = parts[2]
                ok = deliver(target, key) if key else False
                if ok:
                    code = order_code(target, key)
                    store.mark_paid(code)
                    store.mark_delivered(code)
                store.log_event(target, "give_manual", {"by": uid, "ok": ok})
                send(chat_id, "Видано" if ok
                     else "Не вдалося. " + pname(key) + ": " + ready_text(key))
            return "ok"
    except Exception as e:
        log.exception("update failed: %s", e)
    finally:
        store.session_end()
    return "ok"


def ensure_webhook():
    """Ставимо завжди: після серії таймаутів телеграм іде в довгу паузу."""
    try:
        r = api("setWebhook", url=BASE_URL + "/" + SECRET,
                allowed_updates=["message", "callback_query"])
        log.info("вебхук поставлений: %s", r)
        api("setMyCommands", commands=[
            {"command": "start", "description": "Три схеми світла безкоштовно"},
            {"command": "moi", "description": "Мої матеріали: гайд і уроки"},
        ])
    except Exception as e:
        log.warning("ensure_webhook: %s", e)


if os.getenv("NO_THREADS", "").strip() != "1":
    threading.Thread(target=ensure_webhook, daemon=True).start()
    threading.Thread(target=mono_poll, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
