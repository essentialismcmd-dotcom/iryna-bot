#!/usr/bin/env python3
"""
Бот Iryna Rul. Три речі й нічого більше.

1. Лійка: магніт → гайд «Світло» → канал «для своїх» (там МК), оплата в банку
   Monobank, видача файлів. Тарифи t2/t3 і курси ретуші сплять за перемикачами
   GUIDE_TIERS і COURSES_ON: людина бачить лише те, що продається зараз.
2. Приймання матеріалів від Іри: вона кидає що завгодно з коротким підписом,
   рівно як кидала в особистий чат. Бот приймає і мовчить.
3. База: усе прийняте лежить у Postgres, звідти це дістає Yaro або Клод.

Чого тут свідомо немає: задачника, блоків, меню, кнопок розкладання,
режимів і клавіатур. Вони були, ними ніхто не користувався, 28.08 вирізані.
Правило: у боті лишається те, що працює само, а не те, що вимагає навчання.
"""

import os, re, json, time, html, logging, threading, hmac, hashlib
import requests
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, request

import store
import kabinet_mist   # міст у кабінет курсів; без KABINET_URL і KABINET_KEY вимкнений

TOKEN         = os.environ["BOT_TOKEN"]
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))
IRA_ID        = int(os.getenv("IRA_ID", "0"))
CHANNEL_URL   = os.getenv("CHANNEL_URL", "").strip()
# Замка нема: магніт видається всім одразу, канал просимо після файлу (кнопка
# каналу). CHANNEL_ID це @username каналу або -100…; без змінної береться з
# CHANNEL_URL; з нього виходить посилання на канал, коли CHANNEL_URL не заданий.
CHANNEL_ID    = os.getenv("CHANNEL_ID", "").strip() or (
    "@" + CHANNEL_URL.rstrip("/").rsplit("/", 1)[-1] if "t.me/" in CHANNEL_URL else "")
MAGNET_URL    = os.getenv("MAGNET_URL", "").strip()
# Закріп каналу з кнопкою в бот (слово Yaro 04.10): кнопку під постом каналу
# може поставити лише бот у момент публікації, тож адмін шле боту /zakrip.
# ZAKRIP_CHAT за замовчуванням чернетка каналу; оригінал лише окремим словом Yaro.
ZAKRIP_CHAT   = os.getenv("ZAKRIP_CHAT", "").strip() or "-1004303013438"
# Кнопка закріпу (TYZHDEN-2026-10-05 рядок 72, слово Yaro «Хочу на МК»): веде на ?start=mk.
ZAKRIP_URL    = os.getenv("ZAKRIP_URL", "").strip() or "https://t.me/iryna_rul_bot?start=mk"
ZAKRIP_BTN    = os.getenv("ZAKRIP_BTN", "").strip() or "Хочу на майстер-клас"
# Колір кнопки закріпу (Bot API 9.4, поле style): danger червона, success зелена, primary синя.
# Порожньо = колір за замовчуванням застосунку. Слово кольору першим після /zakrip
# (червона|зелена|синя) перебиває змінну для одного посту. У червоної серце біле.
ZAKRIP_COLORS = {"червона": "danger", "червоний": "danger", "зелена": "success", "зелений": "success",
                 "синя": "primary", "синій": "primary"}
ZAKRIP_STYLE  = (lambda v: ZAKRIP_COLORS.get(v, v) if ZAKRIP_COLORS.get(v, v) in
                 ("danger", "success", "primary") else "")(os.getenv("ZAKRIP_STYLE", "").strip().lower())
GUIDE_FILE_ID = os.getenv("GUIDE_FILE_ID", "").strip()
# Чинні версії файлів (25.09): гайд v13 і магніт v3d. До цього бот віддавав
# гайд v10 і магніт v2, бо file_id жили тільки в змінних Render і ніхто не
# бачив, яка версія за ними стоїть. Тепер: POST /zalyvka/<S>?rol=guide|magnet
# з файлом, чия назва містить очікуваний шматок, кладе file_id у kv бази, і
# бот віддає його замість змінної. /perevirka і /status кажуть, яка версія.
GUIDE_EXPECT  = os.getenv("GUIDE_EXPECT", "SVITLO-guide-2026-09-23-v13").strip()
MAGNET_EXPECT = os.getenv("MAGNET_EXPECT", "3-skhemy-svitla-2026-09-23-v3d").strip()
# Старі курси ретуші Іра 24.09 назвала застарілими: «тільки за знижкою»,
# «1200 гривень максимум за два». COURSE_BUNDLE_ONLY=1 показує лише пакет.
COURSE_BUNDLE_ONLY = os.getenv("COURSE_BUNDLE_ONLY", "").strip().lower() in ("1", "true", "yes", "on")
# 25.09 (слово Yaro 01:2x): старі курси 1–2 не продаємо, чекаємо новий від Іри.
# Без COURSES_ON=1 (або без PAY_URL, див. courses_sale) курсів нема в меню, слово КУРС і старі кнопки кажуть «готую
# новий», заявок і кодів на k1/k2/k12 бот не дає. Куплене раніше видається як було.
COURSES_ON = os.getenv("COURSES_ON", "").strip().lower() in ("1", "true", "yes", "on")
# Брендинг, рівень 1 (25.09): картинки в стилі гайда v13 до повідомлень лійки.
# Значення: file_id картинки, залитої цьому боту, або https-URL. Порожня змінна:
# бот шле просто текст, як до брендингу. Картинки: cowork projects/iryna/bot/brend/.
START_PIC     = os.getenv("START_PIC", "").strip()     # /start, обкладинка «Привіт, я Іра»
CARD_MAGNIT   = os.getenv("CARD_MAGNIT", "").strip()   # після видачі трьох схем
CARD_GUIDE    = os.getenv("CARD_GUIDE", "").strip()    # гайд «Світло», вибір тарифу
CARD_KANAL    = os.getenv("CARD_KANAL", "").strip()    # крок після гайда і канал
CARD_MK       = os.getenv("CARD_MK", "").strip()       # МК по світлу
CAPTION_MAX   = 1024                                    # ліміт підпису до фото в Telegram
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
# Кому летять заявки на МК і зйомку: це робота Іри, тож сюди можна вписати її id.
LEAD_IDS = _ids(os.getenv("LEAD_IDS", "")) or NOTIFY_IDS

API = "https://api.telegram.org/bot" + TOKEN
MONO = "https://api.monobank.ua"
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")


def _thread_excepthook(args):
    """Будь-який виняток у фоновому потоці потрапляє в лог (раніше йшов лише в stderr)."""
    log.error("виняток у потоці %s", getattr(args.thread, "name", "?"),
              exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


threading.excepthook = _thread_excepthook

HELLO = (
    "Привіт, це Ірина Руль ♥️\n\n"
    "Тут моя добірка «Три схеми світла з одного сетапу».\n"
    "Три різні картинки за одну зйомку, без докупки обладнання.\n\n"
    "Я віддаю її підписникам свого каналу «для своїх». "
    "Тисніть кнопку, надішлю файл."
)
# Людина, що прийшла за посиланням ?start=guide (останні сторінки гайда «Світло»),
# гайд уже має. До 23.09 бот показував їй той самий HELLO з кнопкою «Забрати три
# схеми світла», тобто пропонував магніт назад у лійку. Тепер їй іде наступна
# сходинка, курс ретуші; мітка «guide» і далі пишеться в source_tag і в events.
GUIDE_HELLO = (
    "Привіт, це Ірина Руль ♥️\n\n"
    "Ви прийшли з мого гайда «Світло», отже всі тринадцять схем у вас уже є.\n\n"
    "Наступний крок: світло поставили, далі кадр треба довести в ретуші. "
    "Покажу мій курс ретуші."
)
AFTER = (
    "Готово, файл вище ♥️\n\n"
    "Спробуйте на найближчій зйомці, це пʼять хвилин на студії.\n\n"
    "У каналі «Iryna Rul | для своїх» розбираю світло детальніше і показую бекстейдж зі зйомок.\n"
    "Хочете всі схеми, а не три, тисніть «Хочу повний гайд»."
)
# Канал просимо ПІСЛЯ файлу (ревізія 29.09, З9 §6 п.6): людина спершу отримує
# схеми, потім AFTER з кнопкою каналу. Замка перед файлом нема: він коштував
# 4 натиски і вів у порожнє перше враження. Старі кнопки «Я в каналі» і
# «Спершу файл, канал пізніше» у чатах людей ще живі: віддають файл одразу.
LEGACY_LOCK_DATA = ("lock:check", "lock:free")
GUIDE_INTRO_HEAD = (
    "Повний гайд «Світло» ♥️\n\n"
    "Усі мої робочі схеми, від чистої комерції до кольору.\n"
    "Кожна з розстановкою, налаштуваннями і кадром зі зйомки.\n\n"
)
# Останній рядок за кількістю кнопок: «Три варіанти» лише коли тарифів більше одного.
GUIDE_INTRO_MANY = {2: "Два варіанти, оберіть свій.", 3: "Три варіанти, оберіть свій."}
GUIDE_INTRO_ONE = "Натисніть кнопку нижче, і гайд буде ваш."


def guide_intro(kb):
    n = len(kb.get("inline_keyboard", []))
    return GUIDE_INTRO_HEAD + (GUIDE_INTRO_MANY.get(n, GUIDE_INTRO_MANY[3]) if n > 1 else GUIDE_INTRO_ONE)
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
LESSON_DONE = ("Це весь урок ♥️ Відео дивіться в моєму кабінеті курсів (кнопка вище), "
               "практику відкривайте у Photoshop через Camera Raw і повторюйте за мною. "
               "Питання пишіть сюди.")
LESSON_DONE_CHAT = ("Це весь урок ♥️ Практику відкривайте у Photoshop через Camera Raw "
                    "і повторюйте за мною. Питання пишіть сюди.")
LESSON_CAB = ("{title}\n\n"
              "Відео цього уроку в моєму кабінеті курсів: там плеєр, прогрес "
              "і зручно повертатись. Практику надішлю сюди. Тисніть кнопку.")
MOI_TEXT = "Ваші матеріали ♥️ Тисніть, і надішлю ще раз."
MOI_EMPTY = ("Поки нічого не куплено ♥️ Безкоштовні три схеми світла і курс ретуші "
             "по кнопках нижче.")
COURSE_OWNED = "Курс ретуші вже ваш ♥️ Усе куплене зібране тут, тисніть і дивіться."
NEXT_AFTER_GUIDE = (
    "І ще одне ♥️ Світло поставили, далі кадр треба довести в ретуші.\n"
    "Покажу мій курс ретуші."
)
BROKEN_FILE_TEXT = ("Щось пішло не так з файлом ♥️ "
                    "Уже розбираюсь, надішлю сюди за кілька хвилин.")
CLIENT_TEXT = ("Прийняла ♥️ Якщо це про зйомку, напишіть в інстаграм, "
               "там відповідаю швидше: @iryna_rul_photographer")

CLIENT_TEXT_BUYER = ("Прийняла ♥️ Ваші матеріали нижче, тисніть і дивіться. "
                     "Якщо це про зйомку, напишіть в інстаграм: @iryna_rul_photographer")

# Закріп каналу обіцяє: «напишіть боту слово СВІТЛО, МК або ЗЙОМКА». До 25.09
# бот на ці слова відповідав «напишіть в інстаграм», тобто обіцянка не
# працювала. Тепер слово веде на свою сходинку, заявки МК і зйомки падають
# у LEAD_IDS (без змінної тим самим, кому йдуть заявки на оплату).
KEYWORDS = {
    "світло": "guide", "гайд": "guide",
    "мк": "mk", "майстерклас": "mk", "майстер-клас": "mk",
    "курс": "retush", "ретуш": "retush", "ретушь": "retush",
    "зйомка": "shoot", "зйомку": "shoot",
}
MK_TEXT = (
    "Індивідуальний майстер-клас зі світла ♥️\n\n"
    "У студії, на імпульсному світлі: ставимо схеми під ваш запит, "
    "ви знімаєте самі, я поруч і виправляю. На виході кадри в портфоліо.\n\n"
    "Тисніть кнопку, і я напишу вам особисто: дати, місто, деталі."
)
MK_THANKS = "Записала ♥️ Напишу вам особисто найближчим часом."
SHOOT_TEXT = ("Про зйомку швидше в інстаграмі ♥️ @iryna_rul_photographer, "
              "там відповідаю одразу. Ваше повідомлення я теж бачу.")
# Курсів у продажу нема (25.09): слово КУРС і старі кнопки курсу ведуть на
# гайд і канал, без обіцянок «скоро».
RETUSH_SOON = (
    "Поки що тут усе про світло ♥️\n\n"
    "Тринадцять моїх робочих схем зібрані в гайді «Світло», "
    "а зйомки і бекстейдж показую в каналі «для своїх»."
)
GUIDE_HELLO_NOC = (
    "Привіт, це Ірина Руль ♥️\n\n"
    "Ви прийшли з мого гайда «Світло», отже всі тринадцять схем у вас уже є.\n\n"
    "Далі розбираю світло і показую бекстейдж зі зйомок у каналі «для своїх», кнопка нижче."
)
AFTER_NOC = (
    "Готово, файл вище ♥️\n\n"
    "Спробуйте на найближчій зйомці, це пʼять хвилин на студії.\n\n"
    "У каналі «Iryna Rul | для своїх» розбираю світло детальніше і показую бекстейдж зі зйомок.\n"
    "Хочете всі схеми, а не три, тисніть «Хочу повний гайд»."
)
MOI_EMPTY_NOC = ("Поки нічого не куплено ♥️ Безкоштовні три схеми світла і повний гайд "
                 "по кнопках нижче.")
# Без оплати (PAY_URL порожній, ФОП і банка пізніше, слово Yaro 29.09): бот завершений
# з тим, що є зараз, тобто магніт, канал. Жодних «реквізити», «скоро», «надішлю».
GUIDE_SALE = bool(PAY_URL)


def courses_sale():
    """
    Продаж курсів ретуші: лише коли COURSES_ON і є куди платити. Без PAY_URL
    людина не бачить ні цін, ні кнопок покупки курсу, ні підводок до неї:
    так само, як за вимкненого COURSES_ON. Доступ до вже куплених уроків від
    цього не залежить. Функція, а не константа, бо тести й /perevirka читають
    COURSES_ON і PAY_URL наживо.
    """
    return bool(COURSES_ON and PAY_URL)
AFTER_NOPAY = AFTER_NOC.rsplit("\n", 1)[0]
MOI_EMPTY_NOPAY = "Поки нічого не куплено ♥️ Безкоштовні три схеми світла по кнопці нижче."
PAUSED_TEXT = (
    "Почніть з добірки ♥️ Три схеми світла з одного сетапу, безкоштовно.\n\n"
    "А розбір світла і бекстейдж зі зйомок дивіться в каналі «для своїх»."
)
# Власники курсу: пишуть «я купувала курс» (З9 §6 п.7). Шаблон «напишіть в інстаграм»
# їм не годиться. Є покупка в базі: ведемо до уроків. Нема: чесно кажемо, куди писати.
OWNER_RE = re.compile(r"(купув|купив|купил|купля|придбав|оплатив|оплатил|мій курс|мої курси|мой курс|"
                      r"доступ.{0,20}курс|курс.{0,25}доступ|"
                      # «вже» лише разом з дією власника, не «вже хочу/можна/буде курс»:
                      r"(?:вже|уже)\s+(?:\w+\s+)?(?:проходил\w*|проходив\w*|пройшл\w*|пройшов\w*|пройшёл|прошла|прошёл)|"
                      r"[ув]\s+мене\s+(?:вже\s+|уже\s+)?є\s+(?:\w+\s+)?курс|"
                      r"у\s+меня\s+(?:уже\s+)?есть\s+(?:\w+\s+)?курс)")
OWNER_HAS = "Ваш курс на місці ♥️ Усе, що ви купували, зібране тут, тисніть і дивіться."
OWNER_NONE = ("Дякую, що ви вже з нами ♥️ У цьому боті вашої покупки не бачу, "
              "можливо, курс брали з іншого акаунта Telegram. Напишіть Ірині в інстаграм, "
              "там відповідає швидше: @iryna_rul_photographer, і назвіть, з якого акаунта "
              "чи пошти купували.")
# Після видачі гайда (без курсів): до 25.09 тут було порожньо, людина
# отримувала файл і далі нічого. Тепер наступна сходинка, канал.
NEXT_AFTER_GUIDE_NOC = (
    "Гайд ваш, доступ залишається назавжди ♥️\n\n"
    "Далі розбираю світло і показую бекстейдж у каналі «Iryna Rul | для своїх», "
    "там же майстер-класи.\n"
    "Гайд завжди можна забрати ще раз: /moi."
)
RETUSH_BUNDLE = (
    "Курс ретуші ♥️\n\n"
    "Один цільний курс: основи фотошопу, бʼюті-портрет, ростовий портрет "
    "і фешн-корекція кольору. Знімки для практики додаються."
)


def course_person(uid):
    """Людина прийшла за курсом чи ретушшю (мітка retush/kurs/kurs10): світла їй не показуємо, поки сама не попросить."""
    try:
        return bool(uid) and courses_sale() and store.kv_get("tag:" + str(uid)) in ("retush", "kurs", "kurs10")
    except Exception:
        return False


MOI_EMPTY_COURSE = "Поки нічого не куплено ♥️ Курс ретуші по кнопці нижче."


def moi_empty(uid=None):
    if course_person(uid):
        return MOI_EMPTY_COURSE
    if not GUIDE_SALE:
        return MOI_EMPTY_NOPAY
    return MOI_EMPTY if courses_sale() else MOI_EMPTY_NOC


def keyword(text):
    """Одне слово з закріпу каналу → ключ сходинки, інакше None."""
    t = (text or "").strip().lower()
    if not t or len(t) > 20 or " " in t:
        return None
    t = re.sub(r"[^\w\-]", "", t)
    return KEYWORDS.get(t)


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


def _tier_prices(raw, g):
    """
    t2 і t3 завжди дорожчі за сам гайд. До 25.09 t2 стояв числом 900, рівно як
    t1: після підйому гайда з 650 до 900 розбір кадру став безкоштовним
    додатком. Тепер надбавка до ціни гайда: +300 (розбір кадру 1 200 грн,
    TARYFY-2026-09-05.md) і +1 000 (три кадри), або GUIDE_TIER_PRICES="t2,t3".
    """
    try:
        p = [int(x) for x in raw.replace(" ", "").split(",")]
        if len(p) == 2 and g < p[0] < p[1]:
            return p
    except ValueError:
        pass
    return [g + 300, g + 1000]


_T2, _T3 = _tier_prices(os.getenv("GUIDE_TIER_PRICES", ""), _G)

TIERS = {
    "t1": {"name": "Гайд «Світло»", "uah": _G, "btn": "Гайд, " + str(_G) + " грн",
           "text": ("Гайд «Світло», " + str(_G) + " грн\n\n"
                    "42 сторінки, тринадцять моїх робочих схем: розстановка, "
                    "налаштування і кадр зі зйомки до кожної. Доступ залишається назавжди."),
           "extra": ""},
    "t2": {"name": "Гайд + розбір одного кадру", "uah": _T2, "btn": "Гайд + розбір кадру, " + str(_T2) + " грн",
           "text": ("Гайд «Світло» + розбір одного кадру, " + str(_T2) + " грн\n\n"
                    "Той самий гайд, плюс ви надсилаєте мені один свій знімок, "
                    "і я особисто розбираю, що там зі світлом і що змінити, щоб стало краще."),
           "extra": "Надішліть кадр прямо сюди, я подивлюсь і відповім."},
    "t3": {"name": "Гайд + розбір трьох кадрів", "uah": _T3, "btn": "Гайд + розбір трьох кадрів, " + str(_T3) + " грн",
           "text": ("Гайд «Світло» + розбір трьох кадрів, " + str(_T3) + " грн\n\n"
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

# Слово Yaro 03.10: курс один цільний, 3 300 грн. З COURSE_BUNDLE_ONLY кнопка k12
# продає його одним продуктом (код -6, кабінет відкриває весь курс); ціна
# третім числом COURSE_PRICES, напр. COURSE_PRICES=3200,1900,3300.
if COURSE_BUNDLE_ONLY:
    COURSES["k12"].update({
        "name": "Курс ретуші",
        "btn": "Курс ретуші, " + str(_K12) + " грн",
        "text": ("Курс ретуші, " + str(_K12) + " грн\n\n"
                 "Усередині: 18 відео, близько 135 хвилин, 4 уроки: бʼюті-портрет, "
                 "темний фон, фешн-колір, колір і пресети Іри. "
                 "Доступ назавжди. Увесь курс відкривається одразу після оплати."),
    })

# Один словник на все, що продається. Цифра після дефіса в коді платежу
# це «code»: 1-3 гайд, 4-6 курси. Старі коди IR...-1 читаються як і раніше.
PRODUCTS = {}
for _k, _v in TIERS.items():
    PRODUCTS[_k] = dict(_v, code=_k[-1], product="guide")
for _k, _c in (("k1", "4"), ("k2", "5"), ("k12", "6")):
    PRODUCTS[_k] = dict(COURSES[_k], code=_c, product="course")
# Слово Yaro 08.10: перша покупниця (лід з діректу до анонсу) отримує курс
# зі знижкою 10 % за міткою ?start=kurs10. Окремий продукт з кодом -7, щоб
# банка перевіряла саме знижену суму; видається як звичайний курс k12.
KURS_ZNYZHKA = 10
_K12Z = int(round(_K12 * (100 - KURS_ZNYZHKA) / 100.0))
PRODUCTS["k12z"] = dict(PRODUCTS["k12"], code="7", uah=_K12Z, text=(
    "Курс ретуші, " + str(_K12) + " грн\n"
    "Вам знижка " + str(KURS_ZNYZHKA) + " % як першій учениці на нашій платформі: " + str(_K12Z) + " грн\n\n"
    "Усередині: 18 відео, близько 135 хвилин, 4 уроки: бʼюті-портрет, "
    "темний фон, фешн-колір, колір і пресети Іри. "
    "Доступ назавжди. Увесь курс відкривається одразу після оплати."))
PRODUCTS["k12z"]["name"] = PRODUCTS["k12"]["name"] + " (знижка " + str(KURS_ZNYZHKA) + " %)"
BY_CODE = {v["code"]: k for k, v in PRODUCTS.items()}

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CODE_RE = re.compile(r"IR([0-9A-Z]+)-([1-7])", re.I)


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


_tm = threading.local()   # таймінг Telegram API в межах одного вебхука


# Постійна кнопка «Мої матеріали» (12.10, правка Б): стоїть під полем вводу в приватному чаті
# людини. Додаємо до повідомлень БЕЗ власної клавіатури, лише тому, хто зараз пише боту
# (_tm.person), і не Ірі. Сповіщення персоналу (інший chat_id) її не отримують.
PERSIST_KB = {"keyboard": [[{"text": "Мої матеріали"}]], "resize_keyboard": True,
              "is_persistent": True}
PERSIST_METHODS = ("sendMessage", "sendPhoto", "sendDocument", "sendVideo")
# 13.10 (слово Yaro: «для всіх завжди», «завжди на виду»): кнопка в кожного з першого /start.
# Вітання має свою інлайн-кнопку, а повідомлення несе лише одну клавіатуру, тож тоді кнопку
# везе окремий рядок-носій (текст з видачі курсу). Коли якась відповідь апдейту і так без
# своєї клавіатури, кнопка їде на ній, і рядка нема (pkb_finish).
PERSIST_LINE = "Усе куплене завжди під рукою в меню «Мої матеріали»."
_pkb_done = set()    # кому кнопку вже віддано (прапорець pkb:<id> у kv); у памʼяті, щоб не питати базу щоразу


def api_raw(method, **params):
    """Сира відповідь Telegram: {ok, result | description, error_code}."""
    params = {k: v for k, v in params.items() if v is not None}
    if (method in PERSIST_METHODS and "reply_markup" not in params
            and params.get("chat_id") is not None
            and params.get("chat_id") == getattr(_tm, "person", None)):
        params["reply_markup"] = PERSIST_KB
    t0 = time.time()
    try:
        r = requests.post(API + "/" + method, json=params, timeout=20)
        j = r.json()
        if params.get("reply_markup") is PERSIST_KB and j.get("ok"):
            _tm.pkb_sent = params.get("chat_id")     # кнопка в цьому апдейті вже доїхала
        return j
    except Exception as e:
        return {"ok": False, "description": str(e)}
    finally:
        dt = time.time() - t0
        _tm.tg_s = getattr(_tm, "tg_s", 0.0) + dt
        _tm.tg_n = getattr(_tm, "tg_n", 0) + 1
        tr = getattr(_tm, "trace", None)
        if tr is not None:
            tr.append("%s %.2fс" % (method, dt))
            log.info("TRACE upd=%s +%.2fс виклик %s %.2fс", getattr(_tm, "upd", "?"),
                     time.time() - getattr(_tm, "t0", t0), method, dt)


def bg(fn, *args, **kw):
    """Виконати в фоновому потоці, щоб перша відповідь людині не чекала на запис у
    базу і сповіщення персоналу. Потік має власне зʼєднання з базою."""
    upd0, t00 = getattr(_tm, "upd", None), getattr(_tm, "t0", None)
    person0 = getattr(_tm, "person", None)

    def run():
        _tm.upd, _tm.t0, _tm.trace = upd0, t00 or time.time(), []
        _tm.person = person0
        tb = time.time()
        store.session_begin()
        try:
            fn(*args, **kw)
        except Exception as e:
            log.warning("bg %s: %s", getattr(fn, "__name__", fn), e)
        finally:
            store.session_end()
            log.info("TRACE upd=%s фон %s: старт +%.2fс, тривав %.2fс, виклики: %s", upd0,
                     getattr(fn, "__name__", fn), tb - (t00 or tb), time.time() - tb,
                     "; ".join(_tm.trace) or "-")
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def api(method, retry=False, **params):
    """
    retry=True тільки для видачі файлів: на 429 бот чекає стільки, скільки
    просить Telegram, і пробує ще раз. Відповіді в чат так не повторюємо,
    інакше один флуд від адміна заблокує потік вебхука на пів хвилини.
    """
    j = api_raw(method, **params)
    for _ in range(3 if retry else 0):
        if j.get("ok") or j.get("error_code") != 429:
            break
        wait = (j.get("parameters") or {}).get("retry_after") or 3
        if wait > 60:
            break
        log.info("429 %s: чекаємо retry_after=%s", method, wait)
        time.sleep(wait + 0.3)
        j = api_raw(method, **params)
    if not j.get("ok"):
        log.warning("%s: %s", method, j.get("description"))
    return j.get("result")


def send(chat_id, text, markup=None):
    return api("sendMessage", chat_id=chat_id, text=text,
               reply_markup=markup, disable_web_page_preview=True)


def pkb_has(uid):
    """Чи людина вже отримала постійну кнопку: прапорець pkb:<id> у kv (з 13.10)."""
    if uid in _pkb_done:
        return True
    try:
        v = store.kv_get("pkb:" + str(uid))
    except Exception:
        v = None
    if v:
        _pkb_done.add(uid)
    return bool(v)


def pkb_mark(uid):
    if uid in _pkb_done:
        return
    _pkb_done.add(uid)      # і без бази в цьому процесі рядок не повториться
    try:
        store.kv_set("pkb:" + str(uid), "1")
    except Exception as e:
        log.warning("pkb %s: %s", uid, e)


def pkb_finish():
    """Кінець апдейту людини, якій потрібна постійна кнопка: рівно один раз за апдейт.
    Якщо кнопка вже доїхала на відповіді без своєї клавіатури, рядка-носія нема."""
    cid, _tm.pkb_need = _tm.pkb_need, None
    if getattr(_tm, "pkb_sent", None) != cid:
        api("sendMessage", chat_id=cid, text=PERSIST_LINE, reply_markup=PERSIST_KB,
            disable_web_page_preview=True)
    if getattr(_tm, "pkb_sent", None) == cid:
        pkb_mark(cid)


TAGS_STICKY = ("retush", "kurs", "kurs10", "mk", "guide")
# Персональні мітки партнерів (12.10): ?start=retush_<імʼя> дає той самий шлях, що ?start=retush,
# а source_tag у базі лишається «retush_<імʼя>». Новий партнер працює без коду; підпис у сповіщенні
# «від <імʼя>», для відомих імен нижче гарніший.
PARTNER_TAG_RE = re.compile(r"retush_([A-Za-z0-9]{1,30})")
PARTNERS = {"liza": "Лізи (liza.khbchk)"}

# Посилання для тих, хто купує МК в Іри (слово Yaro 13.10: «щоб там всі доступи у неї відразу
# безкоштовно були», «Гайд і курс», «курс для них має бути відкритий на завжди»):
# ?start=mk_<код> одразу дає гайд «Світло» (t1) і курс ретуші (k12) без оплати, назавжди.
# MK_LINK="код,місць,РРРР-ММ-ДД" лише на Render (репозиторій публічний, коду тут нема);
# дата це останній день за Києвом. Погана змінна = посилання закрите.
def mk_link(raw):
    """«код,місць,РРРР-ММ-ДД» → (код, місць, дата); погане поле дає "" чи 0, тобто закрите."""
    p = [x.strip() for x in (raw or "").split(",")] + ["", "", ""]
    code = p[0].lower() if re.fullmatch(r"[a-z0-9]{6,40}", p[0].lower()) else ""
    return code, _price(p[1], 0), (p[2] if re.fullmatch(r"\d{4}-\d\d-\d\d", p[2]) else "")


MK_CODE, MK_SEATS, MK_UNTIL = mk_link(os.getenv("MK_LINK", ""))
MK_TAG = "mk_link"        # мітка в базі й подіях замість коду
# Текст дослівно (13.10): гайд і курс входять у МК, тож не подарунок і без «платити нічого не треба».
MK_HELLO = ("Дякую, що обрали мій майстер-клас! Гайд «Світло» і курс ретуші входять у нього і тепер "
            "ваші назавжди. Нижче гайд і перший урок курсу, решта уроків у кабінеті.")
MK_AGAIN = "Гайд і курс уже у вас ♥️ Уроки нижче і в кабінеті."
MK_SHUT = "Посилання вже не діє, але я отримала ваш запит і відкрию доступ вручну ♥️"


def send_card_file(chat_id, path, text, markup=None):
    """Картка з локального файла (Telegram не завжди тягне наш URL): перший раз
    заливаємо файлом, далі file_id з kv."""
    key = "pic:" + os.path.basename(path)
    fid = store.kv_get(key)
    if fid:
        return send_card(chat_id, fid, text, markup)
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), path), "rb") as f:
            j = requests.post(API + "/sendPhoto", data={
                "chat_id": chat_id, "caption": text,
                "reply_markup": json.dumps(markup) if markup else ""},
                files={"photo": f}, timeout=30).json()
        if j.get("ok"):
            ph = (j.get("result") or {}).get("photo") or []
            if ph:
                store.kv_set(key, ph[-1]["file_id"])
            return j["result"]
        log.warning("send_card_file: %s", j.get("description"))
    except Exception as e:
        log.warning("send_card_file: %s", e)
    return send(chat_id, text, markup)


def _pic_key(pic):
    return "pic:url:" + hashlib.md5(pic.encode()).hexdigest()[:16]


def send_card(chat_id, pic, text, markup=None):
    """
    Картка з підписом: фото + той самий текст і ті самі кнопки. Без картинки,
    з текстом довшим за підпис (1024) або коли Telegram не прийняв фото,
    іде звичайний send(), тобто лійка не стає ніколи.
    """
    if pic and len(text) <= CAPTION_MAX:
        # URL-картинку Telegram щоразу тягне сам (повільно); після першого разу шлемо кешований file_id
        url = pic.startswith("http")
        fid = store.kv_get(_pic_key(pic)) if url else None
        r = api("sendPhoto", chat_id=chat_id, photo=fid or pic, caption=text, reply_markup=markup)
        if not r and fid:
            r = api("sendPhoto", chat_id=chat_id, photo=pic, caption=text, reply_markup=markup)
            fid = None
        if r:
            if url and not fid:
                ph = r.get("photo") or []
                if ph:
                    bg(store.kv_set, _pic_key(pic), ph[-1]["file_id"])
            return r
    return send(chat_id, text, markup)


def _staff_send(ids, text, markup=None):
    """Сповіщення персоналу без постійної кнопки, навіть коли пише сам адмін (13.10)."""
    person, _tm.person = getattr(_tm, "person", None), None
    try:
        for cid in ids:
            send(cid, text, markup)
    finally:
        _tm.person = person


def notify_lead(text):
    _staff_send(LEAD_IDS, text)


def notify(text, markup=None):
    _staff_send(NOTIFY_IDS, text, markup)


def who(u):
    uname = u.get("username")
    tag = "@" + uname if uname else "без юзернейма"
    name = " ".join([x for x in [u.get("first_name"), u.get("last_name")] if x]) or "без імені"
    return name + ", " + tag + ", id " + str(u.get("id"))


# ---------- живий фідбек: людина -> Іра/адмін, відповідь reply -> людині ----------

_fb_map = {}      # (chat_id, message_id) у чаті персоналу -> id людини
_fb_albums = {}   # media_group_id -> коли надіслали підпис
_ID_RE = re.compile(r"(?:^|\W)id (\d{5,})")


def staff_ids():
    ids = list(NOTIFY_IDS)
    if IRA_ID and IRA_ID not in ids:
        ids.append(IRA_ID)
    return ids


def _fb_remember(cid, res, uid):
    mid = (res or {}).get("message_id") if isinstance(res, dict) else None
    if mid:
        _fb_map[(cid, mid)] = uid
        if len(_fb_map) > 5000:
            for k in list(_fb_map)[:2000]:
                _fb_map.pop(k, None)


def forward_to_staff(m, chat_id, u):
    """Файл/фото/відео людини: підпис (хто, чи купила курс) + forwardMessage усім."""
    uid = u.get("id")
    gid = m.get("media_group_id")
    head = True
    if gid:
        head = str(gid) not in _fb_albums
        _fb_albums[str(gid)] = time.time()
        if len(_fb_albums) > 200:
            for k in list(_fb_albums)[:100]:
                _fb_albums.pop(k, None)
    owned = owned_keys(uid)
    tag = "купила курс" if ({"k1", "k2"} & owned) else "курс не купувала"
    cap = (m.get("caption") or "").strip()
    for cid in staff_ids():
        if head:
            _fb_remember(cid, send(cid, "Від " + who(u) + " (" + tag + ")"
                                   + (":\n" + cap if cap else "")
                                   + "\nВідповідь: reply на це або на файл нижче."), uid)
        _fb_remember(cid, api("forwardMessage", chat_id=cid, from_chat_id=chat_id,
                              message_id=m.get("message_id")), uid)


def fb_target(rep):
    """Кому адресована відповідь: з пам'яті, з forward_origin або з рядка «id N» у підписі."""
    if not rep:
        return None
    t = _fb_map.get((rep.get("_chat"), rep.get("message_id")))
    if t:
        return t
    fo = rep.get("forward_origin") or {}
    su = fo.get("sender_user") or {}
    if su.get("id"):
        return su["id"]
    mt = _ID_RE.search(rep.get("text") or rep.get("caption") or "")
    return int(mt.group(1)) if mt else None


def staff_reply(m, chat_id):
    """Reply персоналу на переслане/сповіщення -> copyMessage людині. True, якщо оброблено."""
    rep = m.get("reply_to_message")
    if not rep:
        return False
    rep = dict(rep, _chat=chat_id)
    target = fb_target(rep)
    if not target or target in staff_ids():
        return False
    r = api_raw("copyMessage", chat_id=target, from_chat_id=chat_id,
                message_id=m.get("message_id"))
    if not r.get("ok"):
        send(chat_id, "Не вдалось надіслати людині: " + str(r.get("description")))
    return True


# ---------- лійка ----------

def magnet_kb():
    return {"inline_keyboard": [[{"text": "Забрати три схеми світла", "callback_data": "magnet"}]]}


def guide_kb():
    """Людині з гайда: перша кнопка курс ретуші, магніта в ній нема навмисно."""
    rows = [[{"text": "Курс ретуші", "callback_data": "retush"}]] if courses_sale() else []
    if CHANNEL_URL:
        rows.append([{"text": "Канал «для своїх»", "url": CHANNEL_URL}])
    return {"inline_keyboard": rows}


def _lock_url():
    return CHANNEL_URL or "https://t.me/" + CHANNEL_ID.lstrip("@")


def guide_rows():
    """Кнопка гайда лише поки є куди платити: без PAY_URL її нема (тупик каси, З9 §6 п.1)."""
    if not GUIDE_SALE:
        return []
    return [[{"text": "Хочу повний гайд «Світло»", "callback_data": "guide"}]]


def paused_kb():
    """Замість гайда: безкоштовні схеми і канал."""
    return {"inline_keyboard": [[{"text": "Забрати три схеми світла", "callback_data": "magnet"}]]
            + channel_rows()}


def send_paused(chat_id):
    send(chat_id, PAUSED_TEXT, paused_kb())


def after_kb():
    rows = []
    if CHANNEL_URL:
        rows.append([{"text": "Канал «для своїх»", "url": CHANNEL_URL}])
    rows += guide_rows()
    if courses_sale():
        rows.append([{"text": "Курс ретуші", "callback_data": "retush"}])
    return {"inline_keyboard": rows}


def active_tiers():
    return [k for k in ("t1", "t2", "t3") if k in GUIDE_TIERS] or ["t1"]


def tiers_kb():
    return {"inline_keyboard": [[{"text": TIERS[k]["btn"], "callback_data": k}]
                                for k in active_tiers()]}


def retush_kb():
    return {"inline_keyboard": [
        [{"text": "Тільки починаю", "callback_data": "q:new"}],
        [{"text": "Вже працюю у фотошопі", "callback_data": "q:pro"}],
    ]}


def course_kb(first):
    """Рекомендований курс першою кнопкою, «обидва» завжди другою."""
    return {"inline_keyboard": [[{"text": COURSES[first]["btn"], "callback_data": first}],
                                [{"text": COURSES["k12"]["btn"], "callback_data": "k12"}]]}


def send_retush(chat_id, uid=None, u=None):
    """Курс ретуші: кваліфікатор або, з COURSE_BUNDLE_ONLY, одразу картка зі знижкою."""
    if not courses_sale():
        send(chat_id, RETUSH_SOON, retush_off_kb())
        return
    if COURSE_BUNDLE_ONLY and uid:
        pick_product(chat_id, uid, u or {}, "k12")
        return
    if COURSE_BUNDLE_ONLY:
        send(chat_id, RETUSH_BUNDLE, {"inline_keyboard": [
            [{"text": COURSES["k12"]["btn"], "callback_data": "k12"}]]})
    else:
        send(chat_id, RETUSH_INTRO, retush_kb())


def pick_product(chat_id, uid, u, data):
    """Картка товару з кодом платежу і кнопкою оплати (кнопка тарифу і /start kurs)."""
    # 08.10, слово Yaro: знижка 10 % поки для всіх, кожен бачить її як особисту.
    if data == "k12" and COURSE_BUNDLE_ONLY:
        data = "k12z"
    t = PRODUCTS[data]
    code = order_code(uid, data)
    store.add_purchase(uid, t["product"], tier=data, order_code=code,
                       amount_uah=t["uah"])
    store.log_event(uid, "tier_pick", {"tier": data, "code": code})
    body = t["text"] + "\n\nПризначення платежу, впишіть його дослівно:\n" + code
    if PAY_URL:
        body += ("\n\nПісля оплати курс відкриється тут, зазвичай протягом кількох хвилин."
                 if t["product"] == "course" else
                 "\n\nПісля оплати файл прийде сюди, зазвичай протягом кількох хвилин.")
    send(chat_id, body, pay_kb(data, uid))
    if lead_once(uid, "zayavka:" + data):
        notify("ЗАЯВКА: " + t["name"] + "\n" + who(u) + "\nКод: " + code,
               give_kb(uid, data))


def mk_kb():
    return {"inline_keyboard": [[{"text": "Хочу на майстер-клас", "callback_data": "mk:want"}]]}


def channel_rows():
    return [[{"text": "Канал «для своїх»", "url": CHANNEL_URL}]] if CHANNEL_URL else []


def empty_kb(uid=None):
    """Порожні «Мої матеріали» і будь-який текст: три схеми, гайд, канал.
    Людині з міткою курсу: курс і канал, без світла."""
    if course_person(uid):
        return {"inline_keyboard": [[{"text": "Курс ретуші", "callback_data": "retush"}]] + channel_rows()}
    rows = [[{"text": "Забрати три схеми світла", "callback_data": "magnet"}]]
    if courses_sale():
        rows.append([{"text": "Курс ретуші", "callback_data": "retush"}])
    else:
        rows += guide_rows()
    return {"inline_keyboard": rows + channel_rows()}


def retush_off_kb():
    return {"inline_keyboard": guide_rows() + channel_rows()}


def retush_kb_one():
    return {"inline_keyboard": [[{"text": "Курс ретуші", "callback_data": "retush"}]]}


# Лід-магніт ретуші (MAGNIT-RETUSH-2026-10-08.md, тексти дослівно): без ціни, лише урок 1.5.
RETUSH_MAGNET_HELLO = (
    "Привіт, це Ірина Руль ♥️\n\n"
    "Тут мій урок «Чистка шкіри без втрати текстури» з курсу ретуші, цілком, 12 хвилин.\n"
    "Прибираємо дефекти, шкіра лишається живою, без «пластику».\n\n"
    "Тисніть кнопку, урок відкриється в моєму кабінеті курсів.\n\n"
    "А після уроку на вас чекає маленький подарунок від мене 🎁"
)
GIFT_DONE = (
    "Ви додивились♥️ Як і обіцяла, маленький подарунок: «Три схеми світла з одного сетапу», "
    "три різні картинки за одну зйомку без докупки обладнання. Файл нижче\n\n"
    "Напишіть, як вам урок? Мені важливо♥️"
)
GIFT_LATE = (
    "Урок чекає на вас♥️ 12 хвилин, коли буде зручно. А подарунок віддаю вже зараз: "
    "«Три схеми світла з одного сетапу», файл нижче"
)
GIFT_FROM_H, GIFT_TO_H = 10, 20            # лише денні години за Києвом
GIFT_AFTER_H = 24                           # через скільки годин після входу без done
GIFT_SINCE = os.getenv("GIFT_SINCE", "2026-10-12T12:00:00+00:00")   # раніше зайшлі не чіпаємо
RETUSH_LESSON_PART = "1.5"


def retush_lesson_url():
    """Кабінет одразу на уроці 1.5 (кабінет читає ?p= і відкриває частину за номером)."""
    return kabinet_mist.URL + "/?p=" + RETUSH_LESSON_PART if kabinet_mist.URL else ""


def retush_magnet_kb():
    """Mini App кнопка: Telegram сам передає підписаний initData, вхід без паролів.
    Без KABINET_URL кнопки нема (тоді лише канал), щоб не слати в нікуди."""
    url = retush_lesson_url()
    rows = [[{"text": "Відкрити урок", "web_app": {"url": url}}]] if url else []
    return {"inline_keyboard": rows + channel_rows()}


def pay_url(uid, key):
    """Персональне посилання на банку: сума товару і код людини вже підставлені
    (перевірено 02.10: ?a=сума&t=коментар, є Apple Pay / Google Pay)."""
    if not PAY_URL:
        return ""
    sep = "&" if "?" in PAY_URL else "?"
    return PAY_URL + sep + urlencode({"a": PRODUCTS[key]["uah"], "t": order_code(uid, key)})


def pay_kb(key, uid=None):
    rows = []
    if PAY_URL:
        url = pay_url(uid, key) if uid else PAY_URL
        rows.append([{"text": "Оплатити в кілька кліків" if uid else "Перейти до оплати", "url": url}])
    # Тестова кнопка тільки адмінам: до 14.09 вона стояла всім, і будь-хто
    # міг забрати гайд безкоштовно, поки TEST_MODE увімкнений на проді.
    if TEST_MODE and uid in NOTIFY_IDS:
        rows.append([{"text": "Я оплатив (тест)", "callback_data": "paid:" + key}])
    # Найдорожчий глухий кут лійки: людина заплатила, а файл не прийшов.
    rows.append([{"text": "Оплатив, а файлу немає", "callback_data": "noget:" + key}])
    return {"inline_keyboard": rows}


def give_kb(uid, key, text="Видати вручну"):
    return {"inline_keyboard": [[{"text": text,
                                  "callback_data": "give:" + str(uid) + ":" + key}]]}


_REF_CACHE = {}


def file_ref(rol):
    """
    Що бот віддає як гайд (rol="guide") чи магніт (rol="magnet"): file_id з kv
    бази, залитий через /zalyvka?rol=, важить більше за змінну Render. Кеш на
    хвилину, щоб не ходити в базу на кожну кнопку.
    """
    env = GUIDE_FILE_ID if rol == "guide" else MAGNET_URL
    if not store.ON:
        return env
    now = time.time()
    hit = _REF_CACHE.get(rol)
    if hit and now - hit[1] < 60:
        return hit[0]
    ref = store.kv_get(rol + "_file_id") or env
    _REF_CACHE[rol] = (ref, now)
    return ref


def guide_ref():
    return file_ref("guide")


def magnet_ref():
    return file_ref("magnet")


def version_line(rol):
    """Яка версія стоїть за file_id: чинна, стара чи невідома."""
    expect = GUIDE_EXPECT if rol == "guide" else MAGNET_EXPECT
    ref = file_ref(rol)
    if not ref:
        return "НЕ ЗАДАНИЙ, чекаємо " + expect
    name = None
    if store.ON:
        name = store.kv_get(rol + "_file_name")
        if not name or store.kv_get(rol + "_file_id") != ref:
            a = store.asset_by_file_id(ref)
            name = (a or {}).get("file_name")
    if not name:
        return "версія невідома (file_id зі змінної, імені в базі нема), чекаємо " + expect
    if expect in name:
        return "чинна, " + name
    return "СТАРА ВЕРСІЯ " + name + ", чекаємо " + expect


def give_magnet(chat_id):
    ref = magnet_ref()
    if not ref:
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ♥️")
        return
    if not api("sendDocument", chat_id=chat_id, document=ref):
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ♥️")
        return
    text = AFTER_NOPAY if not GUIDE_SALE else (AFTER if courses_sale() else AFTER_NOC)
    send_card(chat_id, CARD_MAGNIT, text, after_kb())


def give_gift(uid, text):
    """Подарунок людині ретуші: текст, той самий PDF магніту (з кнопкою каналу), позначка магніту.
    Раз назавжди: заявка в kv (атомарна), другий виклик нічого не шле. True = віддали."""
    if not store.kv_claim("gift:" + str(uid)):
        return False
    u = store.get_user(uid) or {}
    if u.get("got_magnet_at"):
        return False                      # схеми вже видані кнопкою
    ref = magnet_ref()
    if not ref:
        log.warning("gift: нема файла магніту для %s", uid)
        return False
    send(uid, text)
    kb = {"inline_keyboard": channel_rows()} if CHANNEL_URL else None
    ok = bool(api("sendDocument", retry=True, chat_id=uid, document=ref, reply_markup=kb))
    if ok:
        store.mark_magnet(uid)
        store.log_event(uid, "magnet", {"via": "gift"})
        kabinet_mist.push_user(uid)
    else:
        log.warning("gift: PDF не пішов до %s", uid)
    return ok


def kyiv_now(now=None):
    now = now or datetime.now(timezone.utc)
    try:
        return now.astimezone(ZoneInfo("Europe/Kyiv"))
    except Exception:
        return now.astimezone(timezone(timedelta(hours=3)))      # жовтень до 25.10: UTC+3


def kyiv_hour(now=None):
    return kyiv_now(now).hour


def gift_late_run(now=None):
    """Раз на десять хвилин (лише 10:00-20:00 Київ): люди з міткою retush*, що зайшли 24+ год тому,
    не додивились (нема done) і не мають схем чи покупок, отримують подарунок один раз."""
    now = now or datetime.now(timezone.utc)
    if not (GIFT_FROM_H <= kyiv_hour(now) < GIFT_TO_H):
        return 0
    skip = [i for i in [ADMIN_ID, IRA_ID] + NOTIFY_IDS + LEAD_IDS if i]
    n = 0
    for uid in store.gift_candidates(GIFT_SINCE, GIFT_AFTER_H, skip) or []:
        if store.kv_get("kp:%s:%s:done" % (uid, RETUSH_LESSON_PART)):
            continue                       # додивилась: подарунок уже пішов або піде з події
        if owned_keys(uid, real=True):
            continue
        try:
            if give_gift(uid, GIFT_LATE):
                n += 1
        except Exception:
            log.exception("gift_late %s", uid)
    return n


def gift_loop():
    STOP.wait(120)
    while not STOP.wait(600):
        store.session_begin()
        try:
            gift_late_run()
        except Exception:
            log.exception("gift_loop")
        finally:
            store.session_end()


def give_guide(uid, tier):
    ref = guide_ref()
    if not ref:
        return False
    if not api("sendDocument", chat_id=uid, document=ref):
        return False
    extra = TIERS.get(tier, {}).get("extra")
    if extra:
        send(uid, extra)
    # Покупець у момент оплати найтепліший, другого такого моменту не буде.
    if courses_sale():
        send(uid, NEXT_AFTER_GUIDE, retush_kb_one())
    else:
        send_card(uid, CARD_KANAL, NEXT_AFTER_GUIDE_NOC, {"inline_keyboard": channel_rows()} if CHANNEL_URL else None)
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


def _send_album(uid, kind, items, caption, pause=1.0):
    """Документи або фото одним альбомом (2–10 штук). Повертає скільки пішло."""
    media = [{"type": kind, "media": fid} for fid in items]
    media[0]["caption"] = caption
    if api("sendMediaGroup", retry=True, chat_id=uid, media=media):
        return len(items)
    # Альбом не пройшов (наприклад, різні типи всередині): віддаємо по одному.
    n = 0
    for j, fid in enumerate(items):
        time.sleep(pause)
        p = {"chat_id": uid, kind: fid}
        if j == 0 and caption:
            p["caption"] = caption
        if api(SEND_BY_KIND[kind], retry=True, **p):
            n += 1
    return n


def owned_keys(uid, real=False):
    """Що людина купила: ключі продуктів з оплачених покупок. Адмін бачить усе
    (real=True: лише справжні покупки, без привілею адміна)."""
    if uid in NOTIFY_IDS and not real:
        return {"t1", "k1", "k2"}
    out = set()
    for p in (store.purchases_of(uid) or []):
        t = p.get("tier") or ""
        if t in ("t1", "t2", "t3"):
            out.add("t1")
        elif t in ("k12", "k12z"):
            out.update({"k1", "k2"})
        elif t in ("k1", "k2"):
            out.add(t)
    return out


def course_owner_reply(chat_id, uid):
    """Покупцю курсу кнопка «Курс ретуші» / слово КУРС / /kurs не веде до оплати вже купленого
    (12.10, правка Б): показуємо його матеріали. True = відповіли."""
    if not ({"k1", "k2"} & owned_keys(uid, real=True)):
        return False
    kb = lessons_kb(uid)
    if not kb:
        return False
    store.log_event(uid, "kurs_owned")
    send(chat_id, COURSE_OWNED, kb)
    return True


def lessons_kb(uid, current=None):
    """Кнопки всіх куплених уроків. current це (ключ, номер), його не показуємо."""
    rows = []
    owned = owned_keys(uid)
    if "t1" in owned and guide_ref():
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


def lesson_cabinet_url(ckey, idx, title):
    """Кабінет на першій частині уроку: номер уроку з заголовка («Урок 2 · ...»), частина N.1.
    Номера нема чи курс другий: просто кабінет (кабінет сам відкриває курс)."""
    if not kabinet_mist.URL:
        return ""
    m = re.match(r"\s*Урок\s*(\d+)", title or "")
    if m and ckey == "k1":
        return kabinet_mist.URL + "/?p=" + m.group(1) + ".1"
    return kabinet_mist.URL + "/"


def send_lesson(uid, ckey, idx):
    """Один урок: відео кнопкою в кабінет (без KABINET_URL файлом у чат), практика альбомом, кнопка «Далі»."""
    sections = COURSE_SECTIONS.get(ckey) or []
    if idx < 0 or idx >= len(sections):
        return False
    title, files = sections[idx]
    total = len(files)
    sent = 0
    cab = lesson_cabinet_url(ckey, idx, title)
    has_video = any(_is_video_item(ckey, idx, kind, fid) for kind, fid in files)
    to_cab = bool(cab and has_video)     # 12.10 (Г): .mov на сотні МБ документом у чат не шлемо
    if to_cab:
        send(uid, LESSON_CAB.format(title=title or "Урок " + str(idx + 1)),
             {"inline_keyboard": [[{"text": "Дивитись урок", "web_app": {"url": cab}}]]})
        time.sleep(1.0)
    elif title:
        send(uid, title)
        time.sleep(1.0)
    docs = []
    for kind, fid in files:
        if _is_video_item(ckey, idx, kind, fid):
            if to_cab:
                sent += 1     # відео віддано кабінетом
                continue
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
    send(uid, LESSON_DONE if to_cab else LESSON_DONE_CHAT, next_kb(ckey, idx))
    store.log_event(uid, "lesson", {"course": ckey, "n": idx + 1, "sent": sent, "of": total})
    return sent > 0


def _is_video_item(ckey, idx, kind, fid):
    return kind in ("video", "animation", "video_note") or fid.startswith("BAAC")         or kind == "document" and _looks_video(ckey, idx, fid)


def practice_items(keys):
    """Матеріали для практики: усе, що в розділах курсу не відео (RAW, .xmp/.acr, PSD).
    Повертає [(заголовок, [(kind, fid)])] лише для розділів, де щось є."""
    out = []
    for ckey in ("k1", "k2"):
        if ckey not in keys:
            continue
        for i, (title, files) in enumerate(COURSE_SECTIONS.get(ckey) or []):
            docs = [(k, f) for k, f in files if not _is_video_item(ckey, i, k, f)]
            if docs:
                out.append((title or ("Урок " + str(i + 1)), docs))
    return out


# Блоки практики (11.10, Іра): файли кожного уроку стоять у кабінеті між підуроками, колір це
# 5 окремих пресетів. Блок це набір розділів курсу за номером у назві: «Урок N ·» і
# «Практика · набір N». Набір 1 це «колір 2121001.raf», який Іра поклала в папку уроку 2;
# набори 2–6 це КОЛІР 1–5 (МАРІЯ32606, ЕВА31164, МК27345, MADINA10956, MADINA10827).
PRACTICE_BLOCKS = {
    "u1": ("k1", [("urok", 1)], "Файли до уроку 1: кадр Єви — RAW, налаштування, готовий PSD"),
    "u2": ("k1", [("urok", 2), ("nabir", 1, "k2")], "Файли до уроку 2: кадр Марії — RAW, налаштування, готовий PSD"),
    "u3": ("k1", [("urok", 3)], "Файли до уроку 3: кадр Мадіни — RAW, налаштування, готовий PSD"),
    "c1": ("k2", [("nabir", 2)], "Колір 1: пресет Іри — RAW і налаштування (.xmp, .acr)"),
    "c2": ("k2", [("nabir", 3)], "Колір 2: пресет Іри — RAW і налаштування (.xmp, .acr)"),
    "c3": ("k2", [("nabir", 4)], "Колір 3: пресет Іри — RAW і налаштування (.xmp)"),
    "c4": ("k2", [("nabir", 5)], "Колір 4: пресет Іри — RAW і налаштування (.xmp, .acr)"),
    "c5": ("k2", [("nabir", 6)], "Колір 5: пресет Іри — RAW і налаштування (.xmp)"),
}
_SEC_RE = {"urok": re.compile(r"^\s*Урок\s+(\d+)(?!\d)"), "nabir": re.compile(r"набір\s+(\d+)(?!\d)", re.I)}


def _section_matches(title, rule):
    m = _SEC_RE[rule[0]].search(title or "")
    return bool(m and int(m.group(1)) == rule[1] and (rule[0] == "nabir" or "практика" in (title or "").lower()))


def block_items(block, keys):
    """Один блок практики: [(підпис, [(kind, fid)])]; порожньо, якщо блоку нема, він не куплений
    або у файлах курсу його розділів нема. Підпис блоку це підпис першого файла альбому.
    Правило може мати свій курс третім елементом (колір 2121001.raf лежить у k2, але Іра
    поклала його в папку уроку 2): без цього курсу його не віддаємо."""
    spec = PRACTICE_BLOCKS.get(block)
    if not spec or spec[0] not in keys:
        return []
    ckey0, rules, label = spec
    docs = []
    for rule in rules:
        ckey = rule[2] if len(rule) > 2 else ckey0
        if ckey not in keys:
            continue
        for i, (title, files) in enumerate(COURSE_SECTIONS.get(ckey) or []):
            if _section_matches(title, rule):
                docs += [(k, f) for k, f in files if not _is_video_item(ckey, i, k, f)]
    return [(label, docs)] if docs else []


def send_practice(uid, block=None):
    """Кнопка кабінету «Отримати в Telegram»: лише практика (без відео), лише покупцям.
    block (u1–u3, c1–c5) шле файли одного блоку, без нього все. Повертає скільки файлів пішло;
    None, якщо людина не має курсу або такого блоку нема.
    Швидко: перше повідомлення одразу, без пауз, документи альбомами по 10, заголовок
    розділу це підпис першого файла альбому; на 429 api(retry=True) чекає retry_after."""
    keys = owned_keys(uid)
    if uid == ADMIN_ID or uid in NOTIFY_IDS:
        keys = set(keys) | {"t1", "k1", "k2"}      # адмін отримує будь-який блок
    items = block_items(block, keys) if block else practice_items(keys)
    if not items:
        why = ("файлів цього блоку в курсі нема" if keys else "немає доступу до курсу")
        log.warning("практика %s: блок %s нічого не шлемо (%s; ключі %s)", uid, block or "all", why, sorted(keys))
        send(uid, ("Не знайшла файлів для цього блоку. Напишіть мені сюди, і я надішлю вручну ♥️" if keys
                   else "Ці файли відкриваються після покупки курсу. Якщо ви вже купили, напишіть мені сюди ♥️"))
        return None
    total = sum(len(d) for _, d in items)
    t0 = time.time()
    send(uid, ("Надсилаю файли: " if block else "Надсилаю матеріали для практики: ") + str(total) + " файлів ♥️")
    sent = 0
    for title, docs in items:
        cap = title
        for kind in ("document", "photo", "audio", "voice"):
            ids = [f for k, f in docs if k == kind]
            for i in range(0, len(ids), 10):
                chunk = ids[i:i + 10]
                log.info("практика %s: +%.1fс «%s» %s x%s", uid, time.time() - t0, title, kind, len(chunk))
                if len(chunk) == 1:
                    p = {"chat_id": uid, kind: chunk[0]}
                    if cap:
                        p["caption"] = cap
                    if api(SEND_BY_KIND[kind], retry=True, **p):
                        sent += 1
                else:
                    sent += _send_album(uid, kind, chunk, cap or "", pause=0)
                cap = ""
    log.info("практика %s: %s з %s файлів за %.1fс", uid, sent, total, time.time() - t0)
    if sent == 0:
        log.warning("практика %s: жоден файл не пішов (блок %s)", uid, block or "all")
        send(uid, "Не вдалося надіслати файли. Спробуйте ще раз за хвилину або напишіть мені сюди ♥️")
    store.log_event(uid, "practice", {"sent": sent, "block": block or "all"})
    return sent


def _looks_video(ckey, idx, fid):
    """Перший файл розділу з «Відео» у назві це відео, навіть якщо залите документом."""
    title = (COURSE_SECTIONS.get(ckey) or [("", [])])[idx][0].lower()
    return title.startswith("відео")


log.info("практика: %s", [(t, len(d)) for t, d in practice_items({"k1", "k2"})])   # без id, лише лічильники


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
    if key == "k12z":
        key = "k12"
    if key in COURSES:
        return give_course(uid, key)
    return give_guide(uid, key)


def give_manual(by, target, key):
    """Ручна видача (кнопка «Видати вручну» і /vydaty): той самий шлях, що й оплата."""
    ok = deliver(target, key) if key else False
    if ok:
        code = order_code(target, key)
        if key in PRODUCTS:
            # Оплата «БЕЗ КОДУ»: тариф не натискали, рядка нема, і без
            # нього ні /moi, ні кабінет покупки не бачать.
            store.ensure_purchase(target, PRODUCTS[key]["product"], tier=key,
                                  order_code=code, amount_uah=PRODUCTS[key]["uah"])
        store.mark_paid(code)
        store.mark_delivered(code)
    store.log_event(target, "give_manual", {"by": by, "ok": ok})
    if ok:
        kabinet_mist.push_user(target)
    return ok


# ---------- посилання МК (13.10) ----------

def mk_code(uid, key):
    """Код МК-видачі: MK, не IR, тож банкою його не оплатити, і в /db це не оплата."""
    return "MK" + b36(uid) + "-" + PRODUCTS[key]["code"]


def mk_guest(uid):
    """Людина отримала гайд і курс за посиланням МК (є МК-рядок курсу)."""
    try:
        return bool(store.get_purchase(mk_code(uid, "k12")))
    except Exception:
        return False


def mk_closed(now=None):
    """Чому посилання МК зараз не дає доступ; порожньо = відкрите."""
    if not MK_CODE:
        return "посилання не задане"
    if MK_SEATS < 1:
        return "місць 0"
    try:
        until = datetime.strptime(MK_UNTIL, "%Y-%m-%d").date()
    except ValueError:
        return "дата погана"
    if kyiv_now(now).date() > until:
        return "дата минула"
    if store.kv_get("mk_off:" + MK_CODE):
        return "зупинено /mk stop"
    return ""


def _mk_rows(uid):
    """Доступ раніше за повідомлення: ціна 0, source_tag «mk» явно (інакше покупка бере мітку
    людини, і курс зарахувався б партнеру), delivered без paid_at. Повтор нічого не дублює."""
    for k in ("t1", "k12"):
        oc = mk_code(uid, k)
        store.add_purchase(uid, PRODUCTS[k]["product"], tier=k, order_code=oc,
                           amount_uah=0, source_tag="mk")
        store.mark_delivered(oc)


def mk_start(chat_id, uid, u, code):
    """/start mk_<код>: гайд і курс одразу й без оплати, одне місце з MK_SEATS на людину."""
    store.touch_user(u, source_tag=MK_TAG)       # людина в базі до покупок (міст кабінету)
    row = store.get_purchase(mk_code(uid, "k12"))
    if row:
        t1 = store.get_purchase(mk_code(uid, "t1")) or {}
        if row.get("status") != "delivered" or t1.get("status") != "delivered":
            _mk_rows(uid)                         # попередня видача обірвалась: дописуємо без нового місця
            kabinet_mist.push_user(uid)
        store.log_event(uid, "mk_again")
        send(chat_id, MK_AGAIN, lessons_kb(uid))
        return
    if not MK_CODE:
        why = "посилання не задане"
    elif not hmac.compare_digest((code or "").strip().lower().encode(), MK_CODE.encode()):
        why = "код не той"
    else:
        why = mk_closed()
    seat = None if why else store.kv_take("mkn:" + MK_CODE, MK_SEATS)
    if not seat:
        why = why or "місць/бази нема"
        shut = "закрите: " + why if why != "місць/бази нема" else why
        store.log_event(uid, "mk_shut", {"why": why})
        send(chat_id, MK_SHUT)
        if lead_once(uid, "mk_shut"):
            notify("МК НЕ видано (" + shut + "): " + who(u),
                   {"inline_keyboard": give_kb(uid, "k12", "Видати курс вручну")["inline_keyboard"]
                    + give_kb(uid, "t1", "Видати гайд вручну")["inline_keyboard"]})
        return
    had = owned_keys(uid, real=True)
    _mk_rows(uid)
    kabinet_mist.push_user(uid)
    ok_g = ok_c = True
    try:
        send(chat_id, MK_HELLO)
        if "t1" not in had:     # не give_guide: там підводка до продажу курсу
            ok_g = bool(guide_ref() and api("sendDocument", retry=True, chat_id=chat_id, document=guide_ref()))
        ok_c = course_owner_reply(chat_id, uid) if {"k1", "k2"} <= had else give_course(uid, "k12")
    except Exception:
        log.exception("mk_start %s", uid)
        ok_g = ok_c = False
    store.log_event(uid, "mk_grant", {"seat": int(seat), "of": MK_SEATS, "had": sorted(had)})
    old = (["гайд"] if "t1" in had else []) + (["курс"] if {"k1", "k2"} & had else [])
    notify("МК: видано, місце " + seat + " з " + str(MK_SEATS) + ": " + who(u)
           + (" (вже мала: " + ", ".join(old) + ")" if old else "")
           + ("" if ok_g else "\nГайд у чат не пішов, доступ у «Мої матеріали» є.")
           + ("" if ok_c else "\nКурс у чат не пішов (" + ready_text("k12") + "), доступ і кабінет є."))


def mk_status():
    """Відповідь /mk персоналу: скільки видано, до якого дня, відкрите чи ні."""
    if not MK_CODE:
        return "Посилання МК не задане: змінна MK_LINK на Render (код,місць,РРРР-ММ-ДД)."
    try:
        until = datetime.strptime(MK_UNTIL, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        until = MK_UNTIL or "?"
    why = mk_closed()
    n = store.kv_get("mkn:" + MK_CODE) if store.ON else None
    if not why and n and n.isdigit() and int(n) >= MK_SEATS:
        why = "місця скінчились"
    return ("Посилання МК: видано " + (n or "0") + " з " + str(MK_SEATS) + ", до " + until
            + " включно (Київ), " + ("відкрите" if not why else "закрите: " + why) + "."
            + ("" if store.ON else " Бази нема: лічильник і /mk stop не зберігаються.")
            + "\n/mk stop закрити, /mk start відкрити знову.")


def ready_text(key):
    if key == "k12z":
        key = "k12"
    if key in COURSES:
        n = len(COURSE_FILES.get(key) or [])
        m = len(COURSE_SECTIONS.get(key) or [])
        return ("у курсі " + str(n) + " файлів у " + str(m) + " розділах") if n else "COURSE1_FILES/COURSE2_FILES не задані"
    return "на місці" if guide_ref() else "GUIDE_FILE_ID не заданий"


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
    if key in PRODUCTS:
        # Оплата з кодом без натиснутого тарифу: рядка покупки нема, mark_paid
        # нічого б не оновив, і ні /moi, ні кабінет не побачили б оплату.
        store.ensure_purchase(uid, PRODUCTS[key]["product"], tier=key,
                              order_code=code, amount_uah=amount // 100)
    store.mark_paid(code, amount // 100)
    ok = deliver(uid, key)
    if ok:
        store.mark_delivered(code)
    store.log_event(uid, "pay_ok" if ok else "pay_undelivered", {"code": code})
    kabinet_mist.push_user(uid)
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
        "Магніт: " + version_line("magnet")
        + " · канал: " + ("кнопка є" if CHANNEL_URL else "CHANNEL_URL не заданий"),
        "Гайд: " + version_line("guide") + " · тарифи " + ",".join(GUIDE_TIERS) + " · "
        + str(_G) + " / " + str(_T2) + " / " + str(_T3) + " грн",
        "Курс 1: " + ready_text("k1") + " · курс 2: " + ready_text("k2"),
        "Ціни курсів: " + str(_K1) + " / " + str(_K2) + " / " + str(_K12) + " грн"
        + (" · тільки пакет" if COURSE_BUNDLE_ONLY else "") + ("" if courses_sale() else " · продаж курсів ВИМКНЕНО" + ("" if PAY_URL else " (каси нема)")),
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
    items = [("гайд t1", "document", guide_ref()), ("магніт", "document", magnet_ref())]
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
        elif fid.startswith("http"):
            out.append(label + ": посилання, getFile його не перевіряє")
        elif "too big" in (j.get("description") or "").lower():
            out.append(label + ": є, понад 20 МБ, " + kind)
        else:
            out.append(label + ": ЗЛАМАНИЙ, " + str(j.get("description")))
    out.append("версія гайда: " + version_line("guide"))
    out.append("версія магніта: " + version_line("magnet"))
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


@app.post("/kabinet-kupyty")
def kabinet_kupyty():
    """Кнопка «Весь курс» у кабінеті (08.10): кабінет просить прислати людині картку курсу
    зі знижкою, фронт одразу згортається і людина бачить картку в чаті. Ключ той самий,
    що в мосту (KABINET_KEY, заголовок X-Kabinet-Key); без ключа ендпоінт мертвий."""
    key = kabinet_mist.KEY
    got = request.headers.get("X-Kabinet-Key", "")
    if not key or not hmac.compare_digest(got, key):
        return "forbidden", 403
    try:
        uid = int((request.get_json(silent=True) or {})["user_id"])
    except Exception:
        return "bad", 400
    store.session_begin()
    try:
        u = dict(store.get_user(uid) or {})
        u["id"] = uid
        store.kv_set("tag:" + str(uid), "retush")   # як /start kurs
        pick_product(uid, uid, u, "k12")
    except Exception:
        log.exception("kabinet-kupyty")
        return "error", 500
    finally:
        store.session_end()
    return "ok"


_prak_busy = set()
_prak_guard = threading.Lock()


@app.post("/kabinet-praktyka")
def kabinet_praktyka():
    """Кнопка «Отримати в Telegram» у кабінеті (11.10): шлемо покупцеві в чат матеріали для
    практики з file_id курсу. Ключ KABINET_KEY (X-Kabinet-Key); без ключа мертвий. Відповідь
    одразу, відправка у фоні (альбоми з паузами); не покупцеві не шлемо нічого."""
    key = kabinet_mist.KEY
    got = request.headers.get("X-Kabinet-Key", "")
    if not key or not hmac.compare_digest(got, key):
        return "forbidden", 403
    try:
        body = request.get_json(silent=True) or {}
        uid = int(body["user_id"])
        block = body.get("block") or None
        if block is not None and block not in PRACTICE_BLOCKS:
            return "bad block", 400
    except Exception:
        return "bad", 400

    log.info("kabinet-praktyka: запит uid=%s блок %s", uid, block or "all")
    # правка А: той самий (людина, блок) не запускаємо вдруге, поки перший іде (повторне натискання в кабінеті)
    with _prak_guard:
        if (uid, block) in _prak_busy:
            log.info("kabinet-praktyka: uid=%s блок %s вже йде, дубль пропущено", uid, block or "all")
            return "ok"
        _prak_busy.add((uid, block))

    def work():
        store.session_begin()
        try:
            log.info("kabinet-praktyka: старт uid=%s", uid)
            log.info("kabinet-praktyka: %s блок %s, пішло %s", uid, block or "all", send_practice(uid, block))
        except BaseException:
            log.exception("kabinet-praktyka: збій uid=%s", uid)
            try:
                send(uid, "Не вдалося надіслати файли. Спробуйте ще раз за хвилину ♥️")
            except Exception:
                pass
        finally:
            with _prak_guard:
                _prak_busy.discard((uid, block))
            store.session_end()

    threading.Thread(target=work, daemon=True).start()
    return "ok"


@app.post("/kabinet-podiia")
def kabinet_podiia():
    """Подія в кабінеті (08.10): людина почала урок (start) чи додивилась (done). Шлемо
    персоналу (NOTIFY_IDS) одне повідомлення; не частіше разу на людину+урок+подію (kv).
    Ключ той самий, що в /kabinet-kupyty; без KABINET_KEY ендпоінт мертвий (403)."""
    key = kabinet_mist.KEY
    got = request.headers.get("X-Kabinet-Key", "")
    if not key or not hmac.compare_digest(got, key):
        return "forbidden", 403
    j = request.get_json(silent=True) or {}
    try:
        uid = int(j["user_id"])
        kind = str(j["kind"])
        lesson = str(j.get("lesson") or "?")[:40]
    except Exception:
        return "bad", 400
    if kind not in ("start", "done"):
        return "bad", 400
    store.session_begin()
    try:
        k = "kp:%s:%s:%s" % (uid, lesson, kind)
        if store.kv_get(k):
            return "dup"
        store.kv_set(k, "1")
        u = dict(store.get_user(uid) or {})
        u["id"] = uid
        uname = u.get("username")
        name = " ".join([x for x in [u.get("first_name"), u.get("last_name")] if x]) or "Без імені"
        tag = "@" + uname if uname else "без юзернейма"
        if kind == "start":
            text = "%s (%s, id %s) почала урок %s" % (name, tag, uid, lesson)
        else:
            mins = j.get("min")
            extra = " (%s хв)" % int(mins) if isinstance(mins, (int, float)) and mins > 0 else ""
            text = "%s (%s, id %s) додивилась урок %s%s" % (name, tag, uid, lesson, extra)
        quiet = mk_guest(uid)       # гості МК (13.10): 18 частин на людину, персоналу і подарунка не шлемо
        if not quiet:
            notify(text)
        if kind == "done" and lesson == RETUSH_LESSON_PART and uid not in staff_ids() and not quiet:
            try:
                if give_gift(uid, GIFT_DONE):
                    notify("Подарунок (три схеми світла) після уроку %s: %s" % (lesson, name))
            except Exception:
                log.exception("gift_done %s", uid)
    except Exception:
        log.exception("kabinet-podiia")
        return "error", 500
    finally:
        store.session_end()
    return "ok"


@app.get("/setup")
def setup():
    base = request.url_root.rstrip("/")
    r = api("setWebhook", url=base + "/" + SECRET,
            allowed_updates=["message", "callback_query"])
    return "setWebhook: " + str(r)


@app.get("/hookinfo/" + SECRET)
def hookinfo():
    i = api("getWebhookInfo") or {}
    d = i.get("last_error_date")
    rows = [
        "url: %s" % (i.get("url") or "ПОРОЖНЬО"),
        "у черзі: %s" % i.get("pending_update_count", "?"),
        "остання помилка: %s" % (i.get("last_error_message") or "немає"),
        "дата помилки (UTC): %s" % (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(d)) if d else "немає"),
        "max_connections: %s" % i.get("max_connections", "?"),
        "ip: %s" % i.get("ip_address", "?"),
    ]
    return "<pre>" + "\n".join(rows) + "</pre>"


STATS_TAGS_MAX = 30       # міток у відповіді, решта одним рядком
STATS_TEXT_MAX = 4000     # ліміт Telegram 4096, лишаємо запас


def _u16(t):
    """Довжина в одиницях UTF-16: так Telegram рахує offset у entities."""
    return len(t.encode("utf-16-le")) // 2


def _zakrip_err(desc):
    low = (desc or "").lower()
    if any(k in low for k in ("not enough rights", "administrator", "chat not found",
                              "forbidden", "not a member", "kicked", "have no rights")):
        return ("Бот не адмін каналу " + ZAKRIP_CHAT + " або не має права публікувати й "
                "закріплювати. Додай бота адміном каналу (Публікація повідомлень, Закріплення) "
                "і надішли /zakrip ще раз.\nTelegram: " + (desc or "без опису"))
    return "Не вийшло: " + (desc or "Telegram не відповів") + ". Спробуй ще раз."


def zakrip(m):
    """
    /zakrip <текст> або reply /zakrip на повідомлення: бот публікує текст у
    ZAKRIP_CHAT з кнопкою-посиланням у бот (?start=mk) і закріплює пост.
    Reply копіює повідомлення як є (фото, форматування); інакше текст після
    команди з тим самим форматуванням (entities зсунуті на довжину команди).
    Повертає відповідь адміну.
    """
    raw = m.get("text") or ""
    parts = raw.split(None, 1)
    body = parts[1] if len(parts) > 1 else ""
    style = ZAKRIP_STYLE
    w = body.split(None, 1)
    if w and w[0].lower().strip(".,:;!") in ZAKRIP_COLORS:
        style = ZAKRIP_COLORS[w[0].lower().strip(".,:;!")]
        body = w[1] if len(w) > 1 else ""
    btn = {"text": ZAKRIP_BTN, "url": ZAKRIP_URL}
    if style:
        btn["style"] = style
        if style == "danger":   # червона кнопка: серце біле
            btn["text"] = re.sub("[\u2665\u2764]\ufe0f?", "\U0001F90D", ZAKRIP_BTN)
    kb = {"inline_keyboard": [[btn]]}
    rep = m.get("reply_to_message")
    if not body.strip() and rep and (rep.get("text") or rep.get("caption") or rep.get("photo")):
        r = api_raw("copyMessage", chat_id=ZAKRIP_CHAT, from_chat_id=m["chat"]["id"],
                    message_id=rep["message_id"], reply_markup=kb)
    elif body.strip():
        cut = _u16(raw[:len(raw) - len(body)])
        ents = [dict(e, offset=e["offset"] - cut) for e in (m.get("entities") or [])
                if e.get("type") != "bot_command" and e.get("offset", 0) >= cut]
        r = api_raw("sendMessage", chat_id=ZAKRIP_CHAT, text=body, entities=ents or None,
                    reply_markup=kb, disable_web_page_preview=True)
    else:
        return ("Надішли /zakrip і текст закріпу одним повідомленням, або відповідай "
                "/zakrip на повідомлення з текстом. Кнопка «" + btn["text"] + "» стане сама. "
                "Колір кнопки: слово червона, зелена чи синя першим після /zakrip.")
    if not r.get("ok"):
        return _zakrip_err(r.get("description"))
    mid = (r.get("result") or {}).get("message_id")
    p = api_raw("pinChatMessage", chat_id=ZAKRIP_CHAT, message_id=mid, disable_notification=True)
    if not p.get("ok"):
        return ("Пост опубліковано (id " + str(mid) + "), але не закріплено. "
                + _zakrip_err(p.get("description")))
    return "Готово, id " + str(mid) + ": пост у " + ZAKRIP_CHAT + " з кнопкою «" + btn["text"] + "»" + (" (" + style + ")" if style else "") + ", закріплено."


def starts_text():
    """
    Скільки людей натиснули /start, з розбивкою за міткою ?start= (inst, chat, guide...).
    Мітку пише людина: у тексті вона лише рядок без переносів, а в HTML її екранує
    stats_page. Відповідь не довша за STATS_TEXT_MAX.
    """
    if not store.ON:
        return "Бази нема (DATABASE_URL не заданий), рахувати нічого."
    d = store.starts_stats([i for i in (ADMIN_ID, IRA_ID) if i])
    if not d:
        return "База не відповіла, спробуйте ще раз."
    magnet = d.get("magnet")
    lines = ["Старти (без адміна й Іри)",
             "Людей: " + str(d["people"]) + ", натисків /start: " + str(d["presses"]),
             "За добу: " + str(d["day"]) + ", за 7 днів: " + str(d["week"]),
             "Отримали магніт: " + (str(magnet) if magnet is not None else "база не відповіла"),
             "",
             "За міткою (людей / натисків):"]
    tags = d.get("tags")
    if tags is None:
        lines.append("  розбивка: база не відповіла, спробуйте ще раз")
    else:
        for r in tags[:STATS_TAGS_MAX]:
            tag = " ".join(str(r.get("tag") or "").split()) or "без мітки"
            lines.append("  " + tag + ": " + str(r["people"]) + " / " + str(r["presses"]))
        rest = tags[STATS_TAGS_MAX:]
        if rest:
            lines.append("  інші (" + str(len(rest)) + " міток): "
                         + str(sum(int(r["people"] or 0) for r in rest)) + " / "
                         + str(sum(int(r["presses"] or 0) for r in rest)))
        if not tags:
            lines.append("  стартів ще нема")
    text = "\n".join(lines)
    return text if len(text) <= STATS_TEXT_MAX else text[:STATS_TEXT_MAX - 1] + "…"


def _pre(text):
    """Текст у HTML-сторінку адміна: усе, що йде з бази чи від людей, екранується."""
    return "<pre>" + html.escape(text, quote=False) + "</pre>"


@app.get("/stats/" + SECRET)
def stats_page():
    store.session_begin()
    try:
        return _pre(starts_text())
    finally:
        store.session_end()


@app.get("/db/" + SECRET)
def db_status():
    return _pre(status_text())


@app.get("/inbox/" + SECRET)
def inbox_page():
    """Усі матеріали з бази рядками «kind:file_id»: з них збираються COURSE*_FILES."""
    store.session_begin()
    try:
        return _pre(assets_lines())
    finally:
        store.session_end()


@app.get("/perevirka/" + SECRET)
def perevirka_page():
    return _pre(perevirka_lines())


@app.get("/stack/" + SECRET)
def stack_page():
    """Діагностика зависань (13.10, staging): стеки всіх потоків через faulthandler,
    без linecache і замків logging (сторож _dump_stuck зависання не показав)."""
    import faulthandler, tempfile
    with tempfile.TemporaryFile("w+") as f:
        faulthandler.dump_traceback(file=f, all_threads=True)
        f.seek(0)
        body = f.read()
    names = {t.ident: t.name for t in threading.enumerate()}
    infl = ["%s: апдейт %s, %.0fс" % (hex(tid), rec[0], time.time() - rec[1]) for tid, rec in list(_inflight.items())]
    return _pre("потоки: " + ", ".join("%s=%s" % (hex(k), v) for k, v in names.items())
                + "\n_inflight: " + ("; ".join(infl) or "порожньо") + "\n\n" + body)


@app.get("/skyd/" + SECRET)
def skyd():
    """
    Чистий лист для одного користувача: /skyd/<S>?uid=<telegram id>.
    Стирає все, що бот про нього памʼятає: рядок users (мітка джерела,
    отриманий магніт), усі його заявки й покупки (тестові й ручні видачі
    теж), журнал подій, памʼять замка каналу. Чужі рядки не чіпає: кожен
    запит має where user_id = uid. Після цього він видаляє чат і тисне
    /start як нова людина. Без uid нічого не робить.
    """
    try:
        uid = int(request.args.get("uid", ""))
    except ValueError:
        return "потрібен ?uid=<telegram id> числом", 400
    if uid <= 0:
        return "потрібен ?uid=<telegram id> числом", 400
    if not store.ON:
        return "бази нема, стирати нічого", 503
    store.session_begin()
    try:
        n = store.wipe_user(uid)
    finally:
        store.session_end()
    _pkb_done.discard(uid)
    if n is None:
        return "база не відповіла, нічого не стерто", 503
    return ("<pre>стерто для " + str(uid) + ": користувач " + str(n.get("users", 0))
            + ", покупки й заявки " + str(n.get("purchases", 0))
            + ", події " + str(n.get("events", 0)) + "\n"
            + "далі: видалити чат з ботом і натиснути /start</pre>")


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
    out = "document:" + fid + "\n" + name + ", " + mb(len(blob)) + "\n"
    # ?rol=guide|magnet: цей файл бот віддає далі замість змінної Render.
    # Тільки коли назва містить чинну версію, щоб v10 не повернувся випадково.
    rol = (request.args.get("rol") or "").strip()
    if rol in ("guide", "magnet"):
        expect = GUIDE_EXPECT if rol == "guide" else MAGNET_EXPECT
        if expect not in name:
            return out + "роль " + rol + " НЕ змінена: у назві нема " + expect + "\n", 409
        if not store.ON:
            return out + "роль " + rol + " НЕ змінена: бази нема\n", 503
        store.session_begin()
        try:
            store.kv_set(rol + "_file_id", fid)
            store.kv_set(rol + "_file_name", name)
        finally:
            store.session_end()
        _REF_CACHE.pop(rol, None)
        out += "роль " + rol + ": бот віддає цей файл\n"
    return out


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


# ---------- дублі (12.10, правка А) ----------
_LOCKED_CB = ("les:", "my:guide", "moi", "magnet", "give:", "paid:", "lock:")
_ulocks = {}
_ulocks_guard = threading.Lock()


def _user_lock(uid, data):
    """Блокування на користувача для видач і меню: les:/moi/my:guide/magnet/give:/paid:.
    Повертає Lock (його бере і знімає hook) або None для решти кнопок."""
    if not uid or not any(data == p or data.startswith(p) for p in _LOCKED_CB):
        return None
    with _ulocks_guard:
        return _ulocks.setdefault(uid, threading.Lock())


def lead_once(uid, kind, hours=24):
    """Заявка персоналу не частіше за раз на `hours` на (людина, тип): повтори кнопок не спамлять.
    True = слати. Без бази (kv) завжди True."""
    key = "lead:" + str(uid) + ":" + kind
    try:
        now = time.time()
        prev = store.kv_get(key)
        if prev and now - float(prev) < hours * 3600:
            return False
        store.kv_set(key, str(now))
    except Exception as e:
        log.warning("lead_once %s: %s", key, e)
    return True


@app.post("/" + SECRET)
def hook():
    upd = request.get_json(silent=True) or {}
    t_hook = time.time()
    _tm.tg_s, _tm.tg_n = 0.0, 0
    _tm.t0, _tm.upd, _tm.trace = t_hook, upd.get("update_id"), []
    _tm.pkb_need = _tm.pkb_sent = None
    _mm = upd.get("message") or (upd.get("callback_query") or {}).get("message") or {}
    log.info("TRACE upd=%s вхід %s лаг_доставки=%s",
             upd.get("update_id"),
             "cb:" + str((upd.get("callback_query") or {}).get("data"))[:20] if "callback_query" in upd
             else "msg:" + str((upd.get("message") or {}).get("text") or "")[:20],
             ("%.1fс" % (t_hook - _mm["date"])) if _mm.get("date") and "message" in upd else "н/д")
    store.timing_reset()
    store.session_begin()
    _inflight[threading.get_ident()] = (upd.get("update_id"), t_hook, False)
    _from = ((upd.get("message") or upd.get("callback_query") or {}).get("from") or {})
    # Іра постійної кнопки не отримує ніколи (13.10: і з вимкненим IRA_ON)
    _tm.person = (_from.get("id") if _from.get("id") and not _from.get("is_bot")
                  and not (IRA_ID and _from.get("id") == IRA_ID) else None)
    _held = None
    try:
        if "message" in upd:
            m = upd["message"]
            chat_id = m["chat"]["id"]
            u = m.get("from", {})
            uid = u.get("id")
            if u.get("is_bot"):
                return "ok"
            text = (m.get("text") or m.get("caption") or "").strip()
            # Постійна кнопка «Мої матеріали» (13.10): кожен приватний /start (з видаленим чатом
            # зникає і кнопка) і перше повідомлення людини без прапорця pkb:<id> отримують її
            # рівно раз, у кінці апдейту (pkb_finish). Натиснута кнопка = вона вже є. Не Ірі.
            if (m.get("chat") or {}).get("type") == "private" and chat_id == uid and uid != IRA_ID:
                if text == "Мої матеріали":
                    pkb_has(uid) or pkb_mark(uid)
                elif text.startswith("/start") or not pkb_has(uid):
                    _tm.pkb_need = chat_id

            # Адмін бачить бот так само, як людина (слово Yaro 25.09): жодних
            # службових команд у Telegram, кошиків і збереження його тексту як
            # «матеріалу» (через це слова СВІТЛО/МК в адміна не спрацьовували).
            # Лишилось одне: /nova стирає його слід, щоб пройти лійку новачком.
            # Службове для очей живе в HTTP: /db, /perevirka, /zalyvka, /skyd.
            # Лічильник стартів: /stats (лише адмін, у меню людей його нема).
            if uid == ADMIN_ID and text.startswith("/stats"):
                send(chat_id, starts_text())
                return "ok"
            # Закріп каналу з кнопкою в бот: /zakrip текст або reply /zakrip.
            if uid == ADMIN_ID and text and text.split()[0].split("@")[0] == "/zakrip":
                store.log_event(uid, "zakrip", {})
                send(chat_id, zakrip(m))
                return "ok"
            # Подарунок: платить інша людина, заявки нема. /vydaty <id> видає курс.
            if uid in NOTIFY_IDS and text.split()[:1] and text.split()[0].split("@")[0] == "/vydaty":
                _parts = text.split() + ["", ""]
                arg = _parts[1]
                # 12.10: другий аргумент «gaid» видає гайд «Світло» (ключ t1), без нього курс k12
                vkey = "t1" if _parts[2].lower() in ("gaid", "guide", "гайд") else "k12"
                if not arg.isdigit():
                    send(chat_id, "Напишіть так: /vydaty 458676312 (курс) або /vydaty 458676312 gaid (гайд «Світло»); id людини зі сповіщення «Новий у боті»")
                    return "ok"
                target = int(arg)
                tu = store.get_user(target) or {}
                name = who({"id": target, "username": tu.get("username"),
                            "first_name": tu.get("first_name"), "last_name": tu.get("last_name")})
                if give_manual(uid, target, vkey):
                    send(chat_id, "Видано: " + name)
                else:
                    send(chat_id, "Не вдалося видати " + name + ". " + pname(vkey) + ": " + ready_text(vkey))
                return "ok"
            # Посилання МК (13.10): /mk скільки видано і чи відкрите, /mk stop закрити, /mk start відкрити.
            if uid in NOTIFY_IDS and text.split()[:1] and text.split()[0].split("@")[0] == "/mk":
                _arg = (text.split() + [""])[1].lower()
                if MK_CODE and _arg in ("stop", "start"):
                    store.kv_set("mk_off:" + MK_CODE, "1" if _arg == "stop" else "")
                send(chat_id, mk_status())
                return "ok"
            if uid == ADMIN_ID and text.startswith("/nova"):
                store.wipe_user(uid)
                _pkb_done.discard(uid)
                send(chat_id, "Чисто. Видали цей чат і зайди в бота заново, побачиш його як нова людина.")
                return "ok"

            # Відповідь Іри чи адміна reply-ем на переслане/сповіщення іде людині
            # (раніше за матеріали Іри, щоб відповідь не потрапила в take_material).
            if (uid in staff_ids() and m.get("reply_to_message")
                    and not text.startswith("/") and staff_reply(m, chat_id)):
                return "ok"

            # Іра: кидає що завгодно, бот приймає і мовчить.
            if uid == IRA_ID and IRA_ON:
                store.touch_user(u, role="ira")
                if text.startswith("/start"):
                    send(chat_id, IRA_HELLO)
                    return "ok"
                take_material(m, chat_id, uid)
                return "ok"

            # Файл/фото/відео людини: Ірі й адміну (живий фідбек по ретуші).
            is_file = extract_file(m)[1] is not None
            if is_file and uid not in staff_ids():
                store.touch_user(u)
                store.log_event(uid, "message", {"text": "[файл] " + text[:300]})
                forward_to_staff(m, chat_id, u)

            if text.startswith("/moi") or text.strip() == "Мої матеріали":
                store.touch_user(u)
                kb = lessons_kb(uid)
                send(chat_id, MOI_TEXT if kb else moi_empty(uid), kb or empty_kb(uid))
                return "ok"

            if text.startswith("/start"):
                parts = text.split(None, 1)
                src = parts[1].strip()[:64] if len(parts) > 1 else ""
                # 12.10: мітка партнера retush_<імʼя> = шлях retush, джерело <імʼя> лишається в базі
                raw_src, partner = src, ""
                _pm = PARTNER_TAG_RE.fullmatch(src)
                if _pm:
                    src, partner = "retush", _pm.group(1).lower()
                if src.startswith("mk_"):
                    raw_src = MK_TAG      # 13.10: код посилання МК не пишемо в базу й події
                analytics_tag = None
                # 08.10: людина з лінки (retush, kurs10...) тисне просто /start і
                # отримувала світло. Повторюємо її останню мітку.
                # Слово Yaro 08.10: людина з kurs/kurs10 це людина ретуші; явний вхід показує
                # картку курсу, а простий /start і повернення після видалення чату дають магніт ретуші.
                if src in TAGS_STICKY:
                    _stick = "retush" if src in ("kurs", "kurs10") else src
                    bg(store.kv_set, "tag:" + str(uid), _stick)
                elif not src:
                    # 11.10 (слово Yaro): голий /start дає стартовий екран. Збережена мітка
                    # mk/guide лише в аналітику (раніше підставляла картку МК); людина ретуші
                    # (08.10) лишає магніт ретуші.
                    _saved = store.kv_get("tag:" + str(uid)) or ""
                    if _saved in ("kurs", "kurs10", "retush"):
                        src = "retush"
                    analytics_tag = _saved
                # запис людини, лог і сповіщення персоналу не затримують перший екран
                def _start_after(uid=uid, u=u, src=src, atag=analytics_tag, raw=raw_src, partner=partner):
                    _t = raw or src or atag or ""
                    rec = store.touch_user(u, source_tag=_t) or {}
                    store.log_event(uid, "start", {"tag": _t})
                    # гість МК: своє сповіщення в mk_start; персонал про себе не сповіщає (13.10:
                    # ритуал /nova + /start з акаунта Yaro будив Іру «Новий у боті: YR…»)
                    if rec.get("is_new", True) and raw != MK_TAG and uid not in staff_ids():
                        notify("Новий у боті: " + who(u) + "\nМітка: " + (raw or "без мітки")
                               + (" (від " + PARTNERS.get(partner, partner) + ")" if partner else ""),
                               give_kb(uid, "k12", "Видати курс вручну") if src in ("retush", "kurs", "kurs10") else None)
                bg(_start_after)
                if src == "guide":
                    bg(store.log_event, uid, "guide_entry", {"tag": src})
                    send_card(chat_id, START_PIC, GUIDE_HELLO if courses_sale() else GUIDE_HELLO_NOC, guide_kb())
                elif src == "retush":
                    # лід-магніт ретуші 08.10: урок 1.5 безкоштовно в кабінеті, без світла і без ціни
                    bg(store.log_event, uid, "retush_entry", {"tag": src})
                    send_card_file(chat_id, "static/retush-12.png", RETUSH_MAGNET_HELLO, retush_magnet_kb())  # обкладинка магніту, без «Студійне світло»
                    kabinet_mist.push_user(uid)   # людина в базі кабінету одразу
                elif src == "mk":
                    # мітка закріпу каналу: одразу опис МК з кнопкою заявки (як слово «МК»)
                    bg(store.log_event, uid, "mk_entry", {"tag": src})
                    send_card(chat_id, CARD_MK, MK_TEXT, mk_kb())
                elif src.startswith("mk_"):
                    mk_start(chat_id, uid, u, src[3:])
                elif src in ("kurs", "kurs10") and course_owner_reply(chat_id, uid):
                    bg(store.log_event, uid, "kurs_entry", {"tag": src})
                elif src == "kurs10" and courses_sale():
                    # лід з діректу 08.10: курс зі знижкою 10 %, оплата на знижену суму
                    bg(store.log_event, uid, "kurs_entry", {"tag": src})
                    pick_product(chat_id, uid, u, "k12z")
                elif src == "kurs" and courses_sale():
                    # мітка з кабінету: одразу пропозиція курсу, без вітання з магнітом
                    bg(store.log_event, uid, "kurs_entry", {"tag": src})
                    if COURSE_BUNDLE_ONLY:
                        pick_product(chat_id, uid, u, "k12")
                    else:
                        send_retush(chat_id)
                else:
                    send_card(chat_id, START_PIC, HELLO, magnet_kb())
            elif text.split("@")[0].strip() == "/kurs":
                store.touch_user(u)
                store.log_event(uid, "kurs_entry", {"tag": "cmd"})
                if course_owner_reply(chat_id, uid):
                    pass
                elif courses_sale() and COURSE_BUNDLE_ONLY:
                    pick_product(chat_id, uid, u, "k12")
                else:
                    send_retush(chat_id)
            elif keyword(text):
                k = keyword(text)
                store.touch_user(u)
                store.log_event(uid, "keyword", {"word": k})
                if k == "guide" and not GUIDE_SALE:
                    send_paused(chat_id)
                elif k == "guide":
                    kb = tiers_kb()
                    send_card(chat_id, CARD_GUIDE, guide_intro(kb), kb)
                elif k == "retush":
                    if not course_owner_reply(chat_id, uid):
                        send_retush(chat_id, uid, u)
                elif k == "mk":
                    send_card(chat_id, CARD_MK, MK_TEXT, mk_kb())
                else:
                    send(chat_id, SHOOT_TEXT)
                    if lead_once(uid, "shoot"):
                        notify_lead("Питають про ЗЙОМКУ: " + who(u))
            else:
                store.touch_user(u)
                store.log_event(uid, "message", {"text": text[:300]})
                if not is_file:
                    ntext = "Повідомлення в боті від " + who(u) + ":\n" + (text or "[не текст]")
                    notify(ntext)
                    if IRA_ID and IRA_ID not in NOTIFY_IDS:
                        _fb_remember(IRA_ID, send(IRA_ID, ntext), uid)
                low = text.lower()
                if "курс" in low and OWNER_RE.search(low):
                    # Людина каже, що вже має курс: не шаблон, а відповідь по суті.
                    store.log_event(uid, "owner_msg")
                    # Покупка є (курс чи гайд) і є що показати: до уроків. Покупка є, а
                    # кнопок нема (файли курсу ще не залиті): «не бачу» не кажемо, бо
                    # бачимо; шаблон «прийняла», адмін уже отримав повідомлення вище.
                    # Покупки нема зовсім: чесно кажемо, куди писати.
                    owned = owned_keys(uid)
                    kb = lessons_kb(uid) if owned else None
                    if kb:
                        send(chat_id, OWNER_HAS, kb)
                    elif owned:
                        send(chat_id, CLIENT_TEXT, empty_kb(uid))
                    else:
                        send(chat_id, OWNER_NONE, empty_kb(uid))
                else:
                    # покупцю (курс чи гайд) під довільним текстом уроки, не «напишіть в інстаграм» (правка Б)
                    kb = lessons_kb(uid) if owned_keys(uid, real=True) else None
                    send(chat_id, CLIENT_TEXT_BUYER if kb else CLIENT_TEXT, kb or empty_kb(uid))
            return "ok"

        if "callback_query" in upd:
            cq = upd["callback_query"]
            data = cq.get("data") or ""
            u = cq.get("from", {})
            uid = u.get("id")
            chat_id = cq["message"]["chat"]["id"]
            if not upd.get("_acked"):     # poll_loop відповідає на натискання одразу, щоб кнопка не крутилась
                api("answerCallbackQuery", callback_query_id=cq["id"])
            _held = _user_lock(uid, data)     # один користувач: видачі та меню по черзі, не паралельно
            if _held:
                _held.acquire()

            if data == "magnet" or data in LEGACY_LOCK_DATA:
                # Файл одразу, канал просимо після нього (AFTER з кнопкою каналу).
                # lock:check і lock:free: старі кнопки замка в чатах, теж віддають файл.
                give_magnet(chat_id)
                store.mark_magnet(uid)
                store.log_event(uid, "magnet", {"legacy": data} if data != "magnet" else None)
                kabinet_mist.push_user(uid)
            elif data == "guide" and not GUIDE_SALE:
                store.log_event(uid, "guide_off")
                send_paused(chat_id)
            elif data in TIERS and not GUIDE_SALE:
                # Стара кнопка «Гайд, 900 грн» у чаті: оплати нема, реквізитів не обіцяємо.
                store.log_event(uid, "tier_off", {"tier": data})
                send_paused(chat_id)
            elif data == "guide":
                store.log_event(uid, "guide_open")
                kb = tiers_kb()
                send_card(chat_id, CARD_GUIDE, guide_intro(kb), kb)
            elif data == "retush":
                store.log_event(uid, "retush_open")
                if not course_owner_reply(chat_id, uid):
                    send_retush(chat_id, uid, u)
            elif data == "mk":
                store.log_event(uid, "mk_open")
                send_card(chat_id, CARD_MK, MK_TEXT, mk_kb())
            elif data == "mk:want":
                store.log_event(uid, "mk_want")
                send(chat_id, MK_THANKS, {"inline_keyboard": channel_rows()} if CHANNEL_URL else None)
                if lead_once(uid, "mk"):
                    notify_lead("ЗАЯВКА НА МК: " + who(u) + "\nНаписати особисто.")
            elif not courses_sale() and (data in ("q:new", "q:pro") or data in COURSES):
                # Стара кнопка курсу в чаті людини: продажу нема, кажемо «готую новий».
                store.log_event(uid, "retush_off", {"data": data})
                send_retush(chat_id)
            elif data in TIERS and data not in active_tiers():
                # Стара кнопка тарифу, який зараз не продається: показуємо чинний гайд.
                store.log_event(uid, "tier_off", {"tier": data})
                kb = tiers_kb()
                send(chat_id, guide_intro(kb), kb)
            elif COURSE_BUNDLE_ONLY and data in ("q:new", "q:pro", "k1", "k2"):
                # Стара кнопка кваліфікатора чи окремого курсу в чаті: продаємо лише цільний курс зі знижкою.
                store.log_event(uid, "retush_old_btn", {"data": data})
                pick_product(chat_id, uid, u, "k12")
            elif data in ("q:new", "q:pro"):
                # Кваліфікатор з її скрипту: новачкам перший курс, решті другий.
                store.log_event(uid, "retush_level", {"level": data[2:]})
                if data == "q:new":
                    send(chat_id, RETUSH_NEW, course_kb("k1"))
                else:
                    send(chat_id, RETUSH_PRO, course_kb("k2"))
            elif data in PRODUCTS:
                pick_product(chat_id, uid, u, data)
            elif data.startswith("noget:"):
                key = data.split(":")[1]
                code = order_code(uid, key)
                send(chat_id, NOGET_TEXT)
                store.log_event(uid, "noget", {"code": code})
                if lead_once(uid, "noget:" + key):
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
                kabinet_mist.push_user(uid)
                notify("ТЕСТ оплати: " + pname(key) + "\n" + who(u))
            elif data == "moi":
                kb = lessons_kb(uid)
                send(chat_id, MOI_TEXT if kb else moi_empty(uid), kb or empty_kb(uid))
            elif data == "my:guide":
                if "t1" in owned_keys(uid) and guide_ref():
                    api("sendDocument", chat_id=chat_id, document=guide_ref())
                else:
                    send(chat_id, moi_empty(uid), empty_kb(uid))
            elif data.startswith("les:"):
                _, ckey, n = (data.split(":") + ["", ""])[:3]
                if ckey in owned_keys(uid):
                    send_lesson(chat_id, ckey, int(n or 0))
                else:
                    send(chat_id, moi_empty(uid), empty_kb(uid))
            elif data.startswith("give:") and uid in NOTIFY_IDS:
                parts = (data.split(":") + ["", ""])[:3]
                target = int(parts[1])
                key = parts[2]
                ok = give_manual(uid, target, key)
                send(chat_id, "Видано" if ok
                     else "Не вдалося. " + pname(key) + ": " + ready_text(key))
            return "ok"
    except Exception as e:
        _tm.pkb_need = None          # відповідь зламалась: рядок-носій сам по собі не шлемо
        log.exception("update failed: %s", e)
    finally:
        if _held:
            _held.release()
        if getattr(_tm, "pkb_need", None):
            try:
                pkb_finish()
            except Exception as e:
                log.warning("постійна кнопка: %s", e)
        _tm.person = None
        _inflight.pop(threading.get_ident(), None)
        store.session_end()
        total = time.time() - t_hook
        if getattr(_tm, "trace", None):
            log.info("TRACE upd=%s кінець %.2fс: %s", _tm.upd, total, "; ".join(_tm.trace))
        if total > 0.8:
            kind = ("cb:" + str((upd.get("callback_query") or {}).get("data"))[:20]
                    if "callback_query" in upd else
                    "msg:" + str(((upd.get("message") or {}).get("text") or "")[:20]))
            dbs, dbn = store.timing_get()
            log.warning("ПОВІЛЬНИЙ вебхук %.2fс (%s): Telegram %.2fс/%d викликів, база %.2fс/%d запитів",
                        total, kind, _tm.tg_s, _tm.tg_n, dbs, dbn)
    return "ok"


PEOPLE_COMMANDS = [
    {"command": "start", "description": "Три схеми світла безкоштовно"},
    {"command": "moi", "description": "Мої матеріали: усе куплене"},
    {"command": "kurs", "description": "Курс ретуші"},
]


def clear_scoped_commands():
    """
    Меню команд людини одне для всіх, адмін теж бачить тільки його.
    Старий код (454d807, 28.08) ставив адміну й Ірі меню з областю дії chat:
    now, todo, inbox, status, export, пізніше blocks і ira. Telegram тримає
    таке меню, доки його не видалити, тому код сам по собі його не прибере:
    знімаємо всі області, що стоять вище за default.
    """
    ids = {i for i in [ADMIN_ID, IRA_ID] + NOTIFY_IDS + LEAD_IDS if i}
    for cid in ids:
        api("deleteMyCommands", scope={"type": "chat", "chat_id": cid})
    api("deleteMyCommands", scope={"type": "all_private_chats"})


# Опис до «Старт» («Що вміє цей бот?») за мовою телеграму людини (слово Yaro
# 08.10): людина з запитом на ретуш не має бачити світло. Українська (типовий
# опис) лишається про світло; ru і en про курс ретуші.
# Пишемо людям завжди українською (слово Yaro 08.10), тому текст один для ru і en.
_OPYS_RETUSH = ("Привіт, я Іра ❤️ Бʼюті і фешн фотограф, знімаю вже 6 років.\n\n"
                "Тут мій курс ретуші: як я доводжу кадр до журнального вигляду. "
                "4 уроки, 18 відео: бʼюті-портрет, темний фон, фешн-колір, колір і мої пресети.\n\n"
                "Увесь курс відкривається одразу після оплати і лишається з вами назавжди. "
                "Дивіться у своєму темпі, надсилайте сюди свою ретуш, підкажу правки.\n\n"
                "Тисніть «Почати»: заберете безкоштовні три схеми світла, а курс ретуші покажу там само.")
# 08.10: і типовий (українська та решта мов) теж про ретуш, поки йде перша
# покупниця з ретуші; опис про світло: brend/TEKSTY-2026-09-25.md.
DESCRIPTIONS = {"": _OPYS_RETUSH, "ru": _OPYS_RETUSH, "en": _OPYS_RETUSH}


def set_descriptions():
    for lang, text in DESCRIPTIONS.items():
        r = (api("setMyDescription", description=text[:512], language_code=lang) if lang
             else api("setMyDescription", description=text[:512]))
        log.info("опис %s: %s", lang, r)


USE_POLLING = os.getenv("USE_POLLING", "1").strip() != "0"   # 11.10: webhook Telegram->Render зависав на ~60 с


_poll_beat = [time.time()]      # серцебиття polling: оновлюється після кожного getUpdates
_poll_gen = [0]                 # покоління потоку: старий потік після перезапуску сам виходить
_poll_offset = [None]           # підтверджений offset живе тут, щоб новий потік не губив і не повторював
_seen_ids = []                  # останні оброблені update_id (дедуплікація при повторній видачі)
_inflight = {}                  # tid -> (update_id, час старту, чи вже скинули стек): для діагностики зависань
_recent = {}                    # (uid, дія) -> час завершення (або inf поки йде): відсів повторних натискань (правка А)
DEDUP_S = 10                    # вікно від завершення, секунд


def _dedup_key(upd):
    """Ключ повторюваної дії людини: кнопка (callback_data) або /start, /moi, /kurs, «Мої матеріали»,
    слово-ключ. Довільний текст не відсіваємо (це можуть бути різні повідомлення)."""
    cq = upd.get("callback_query")
    if cq:
        uid = (cq.get("from") or {}).get("id")
        data = cq.get("data") or ""
        return (uid, "cb:" + data) if uid and data else None
    m = upd.get("message") or {}
    uid = (m.get("from") or {}).get("id")
    t = (m.get("text") or "").strip()
    if not uid or not t or m.get("reply_to_message"):
        return None
    head = t.split("@")[0].lower() if t.startswith("/") else t.lower()
    if t.startswith("/start") or t.startswith("/moi") or head == "/kurs" or head == "мої матеріали" or keyword(t):
        return (uid, "msg:" + head[:64])
    return None


def _is_dup(key, now):
    """True, якщо ту саму дію цієї людини ще виконують або закінчили менше DEDUP_S тому."""
    if not key:
        return False
    t = _recent.get(key)
    return t is not None and (t == float("inf") or now - t < DEDUP_S)


def _dump_stuck(limit=25):
    """Стек потоків, що тримають апдейт довше за limit секунд (одноразово на апдейт)."""
    import sys, traceback
    now = time.time()
    frames = sys._current_frames()
    for tid, rec in list(_inflight.items()):
        uid_, t0, dumped = rec
        if dumped or now - t0 < limit:
            continue
        _inflight[tid] = (uid_, t0, True)
        fr = frames.get(tid)
        log.error("ЗАВИС апдейт %s вже %.0fс, стек:\n%s", uid_, now - t0,
                  "".join(traceback.format_stack(fr)) if fr else "потоку нема")


def poll_loop(gen=None):
    """
    Long polling замість вебхука: Telegram віддає апдейт одразу, без його таймаутів і пауз
    після помилок доставки (11.10 о 16:28 вебхук мовчав ~60 с: «Read timeout expired»).
    Апдейт передається тому самому обробнику hook() локальним запитом, логіка не змінена.
    12.10: offset підтверджуємо лише ПІСЛЯ обробки пачки (раніше одразу після отримання, і
    апдейти в черзі пулу гинули при рестарті); дубль update_id пропускаємо.
    """
    from concurrent.futures import ThreadPoolExecutor, wait
    if gen is None:
        _poll_gen[0] += 1
        gen = _poll_gen[0]
    pool = ThreadPoolExecutor(max_workers=3)
    pool_ack = ThreadPoolExecutor(max_workers=2)
    url = "http://127.0.0.1:" + os.getenv("PORT", "10000") + "/" + SECRET

    def deliver(upd):
        uid_ = upd.get("update_id")
        try:
            requests.post(url, json=upd, timeout=60)
        except requests.exceptions.ConnectionError:
            # сервер уже закрив прийом (деплой): віддаємо апдейт обробнику напряму, не губимо
            try:
                app.test_client().post("/" + SECRET, json=upd)
            except Exception as e:
                log.warning("poll: апдейт %s не передано: %s", uid_, e)
        except Exception as e:
            log.warning("poll: передача апдейту %s: %s", uid_, e)

    while not STOP.is_set() and gen == _poll_gen[0]:
        try:
            j = requests.post(API + "/getUpdates", timeout=65, json={
                "offset": _poll_offset[0], "timeout": 50,
                "allowed_updates": ["message", "callback_query"]}).json()
            _poll_beat[0] = time.time()
            if not j.get("ok"):
                if j.get("error_code") == 409 or "Conflict" in str(j.get("description")):
                    log.warning("getUpdates 409 Conflict (другий інстанс на деплої?): %s", j.get("description"))
                else:
                    log.warning("getUpdates: %s", j.get("description"))
                STOP.wait(3)
                continue
            batch = [u for u in (j.get("result") or []) if u["update_id"] not in _seen_ids]
            if j.get("result"):
                log.info("getUpdates: %s апдейтів, id %s..%s, нових %s", len(j["result"]),
                         j["result"][0]["update_id"], j["result"][-1]["update_id"], len(batch))
            for upd in batch:     # правка А: id запам'ятовуємо при отриманні, а не після обробки
                _seen_ids.append(upd["update_id"])
            del _seen_ids[:-200]
            futs, keys = [], []
            now = time.time()
            for upd in batch:
                cq = upd.get("callback_query")
                if cq and cq.get("id"):
                    # кнопка перестає крутитись одразу, навіть якщо пул зайнятий довгим уроком
                    upd["_acked"] = True
                    pool_ack.submit(api, "answerCallbackQuery", callback_query_id=cq["id"])
                key = _dedup_key(upd)
                if _is_dup(key, now):
                    log.info("дубль %s від людини відсіяно (update %s)", key, upd["update_id"])
                    continue
                if key:
                    _recent[key] = float("inf")
                    keys.append(key)
                m = upd.get("message") or {}
                if m.get("date"):
                    log.info("TRACE upd=%s отримано polling, лаг від Telegram %.1fс",
                             upd["update_id"], time.time() - m["date"])
                futs.append(pool.submit(deliver, upd))
            done, not_done = wait(futs, timeout=70)
            if not_done:
                log.error("poll: %s апдейтів не оброблено за 70с, йдемо далі", len(not_done))
            end = time.time()
            for key in keys:
                _recent[key] = end
            for k in [k for k, t in _recent.items() if t != float("inf") and end - t > 120]:
                _recent.pop(k, None)
            if j.get("result"):
                _poll_offset[0] = j["result"][-1]["update_id"] + 1    # підтвердження ПІСЛЯ обробки
        except Exception as e:
            log.warning("poll: %s", e)
            STOP.wait(2)
    if STOP.is_set():
        # SIGTERM: нового getUpdates не робимо; вже взяті апдейти дообробляємо,
        # непідтверджені лишаються в Telegram для нового інстансу.
        pool.shutdown(wait=True)
        # підтвердити offset у Telegram, щоб новий інстанс не отримав оброблене вдруге (правка А)
        if _poll_offset[0]:
            try:
                requests.post(API + "/getUpdates", timeout=5, json={
                    "offset": _poll_offset[0], "timeout": 0, "limit": 1,
                    "allowed_updates": ["message", "callback_query"]})
            except Exception as e:
                log.warning("poll: підтвердження offset при зупинці: %s", e)
        log.info("poll: зупинено (SIGTERM), offset %s", _poll_offset[0])
    else:
        pool.shutdown(wait=False)
        pool_ack.shutdown(wait=False)
        log.info("poll: потік покоління %s завершено", gen)


def poll_supervisor():
    """Watchdog: polling без серцебиття 150 с (потік помер чи завис) запускаємо наново;
    заодно скидає в лог стеки зависших обробників апдейтів."""
    def runner(gen):
        while not STOP.is_set() and gen == _poll_gen[0]:
            try:
                poll_loop(gen)
            except BaseException:
                log.exception("poll_loop впав, перезапуск")
                STOP.wait(2)
    _poll_gen[0] += 1
    threading.Thread(target=runner, args=(_poll_gen[0],), daemon=True, name="poll").start()
    _poll_beat[0] = time.time()
    while not STOP.wait(15):
        try:
            _dump_stuck()
            age = time.time() - _poll_beat[0]
            if age > 150:
                log.error("poll: немає серцебиття %.0fс, перезапускаю потік", age)
                _poll_gen[0] += 1
                _poll_beat[0] = time.time()
                threading.Thread(target=runner, args=(_poll_gen[0],), daemon=True, name="poll").start()
        except Exception:
            log.exception("poll_supervisor")


STOP = threading.Event()


def _on_sigterm(signum, frame, _prev=None):
    STOP.set()
    if callable(_prev):
        _prev(signum, frame)


def _hook_sigterm():
    """Ланцюжок до обробника gunicorn: той гасить воркер, ми зупиняємо polling."""
    try:
        import signal
        prev = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda s, f: _on_sigterm(s, f, prev))
    except Exception as e:   # не головний потік (тести)
        log.info("SIGTERM-хук не поставлено: %s", e)


def ensure_webhook():
    """Ставимо завжди: після серії таймаутів телеграм іде в довгу паузу."""
    try:
        if USE_POLLING:
            r = api("deleteWebhook", drop_pending_updates=False)
            log.info("вебхук знято, працюємо через getUpdates: %s", r)
            threading.Thread(target=poll_supervisor, daemon=True, name="poll-supervisor").start()
        else:
            r = api("setWebhook", url=BASE_URL + "/" + SECRET,
                    allowed_updates=["message", "callback_query"])
            log.info("вебхук поставлений: %s", r)
        api("setMyCommands", commands=PEOPLE_COMMANDS)
        clear_scoped_commands()
        set_descriptions()
        # 08.10: кнопка «Кабінет» зліва внизу для всіх (раніше лише в окремих чатах)
        if kabinet_mist.URL:
            api("setChatMenuButton", menu_button={"type": "web_app", "text": "Кабінет",
                                                  "web_app": {"url": kabinet_mist.URL + "/"}})
    except Exception as e:
        log.warning("ensure_webhook: %s", e)


# 13.10: потоки лише ПІСЛЯ fork, у воркері. Render запускає gunicorn з --preload: bot.py імпортує
# майстер, воркер народжується fork-ом. Потоки, запущені при імпорті, працювали в майстрі, і fork
# посеред їхнього першого запиту (requests робить `from netrc import ...`) лишав воркеру замок
# модуля без власника: кожен requests.post у воркері висів назавжди (стек /stack на staging 13.10:
# _lock_unlock_module у requests/utils.py get_netrc_auth). Після кількох деплоїв 13.10 перший апдейт
# висів, а сторож _dump_stuck у майстрі воркерських зависань не бачив. Тепер майстер потоків не
# має зовсім, polling, mono, подарунки й міст кабінету запускає воркер одразу після fork; без
# --preload (імпорт у воркері) і в python bot.py потоки стартують при імпорті, як було.
# Воркер має бути один (--workers 1), інакше кожен тягнув би getUpdates.
_BG = {"started": False}


def _start_background():
    if _BG["started"]:
        return
    _BG["started"] = True
    try:
        _hook_sigterm()
        threading.Thread(target=ensure_webhook, daemon=True).start()
        threading.Thread(target=mono_poll, daemon=True).start()
        threading.Thread(target=gift_loop, daemon=True, name="gift").start()
        kabinet_mist.start()   # звірка з кабінетом раз на годину; без змінних нічого
        log.info("фонові потоки запущено в процесі %s", os.getpid())
    except Exception:
        log.exception("фонові потоки не стартували")


def _bg_after_fork_child():
    _BG["started"] = False
    _start_background()


def _gunicorn_role():
    """«master»: bot.py імпортує майстер gunicorn з --preload (далі fork воркера);
    «worker»: імпорт у воркері (без --preload); "" поза gunicorn."""
    import inspect
    files = [f.filename.replace("\\", "/") for f in inspect.stack(0)]
    if any(p.endswith("gunicorn/workers/base.py") for p in files):
        return "worker"
    if any(p.endswith("gunicorn/arbiter.py") for p in files):
        return "master"
    return ""


if os.getenv("NO_THREADS", "").strip() != "1":
    if _gunicorn_role() == "master" and hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=_bg_after_fork_child)
        log.info("імпорт у майстрі gunicorn (--preload): фонові потоки стартують у воркері після fork")
    else:
        _start_background()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
