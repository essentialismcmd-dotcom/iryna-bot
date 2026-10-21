#!/usr/bin/env python3
"""
Бот Iryna Rul. Три речі й нічого більше.

1. Лійка: магніт → гайд «Світло» → канал «для своїх» (там МК), оплата за
   посиланням Monobank на картку Іри, видача файлів. Тарифи t2/t3 і курси ретуші сплять за перемикачами
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
from concurrent.futures import ThreadPoolExecutor
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
# Воронка після реклами (коворк projects/iryna/VORONKA-2026-10.md, гілка voronka 16.10).
# Обидва прапорці вимикаються на Render без деплою: =0 повертає стару поведінку.
GIFT_FOR_SUB  = os.getenv("GIFT_FOR_SUB", "1").strip().lower() not in ("0", "false", "no", "off")   # п.1: подарунок лише за підписку на канал
PRICE_GATE    = os.getenv("PRICE_GATE", "0").strip().lower() in ("1", "true", "yes", "on")          # 16.10 (мудрець): ворота ціни ВИМКНЕНО за замовчуванням; хто питає про курс, бачить картку з ціною одразу
CHANNEL_URL_RETUSH = os.getenv("CHANNEL_URL_RETUSH", "").strip()   # п.10: окреме запрошення в канал для людей ретуші (рахує вступи з бота)
FREE_LESSON   = os.getenv("FREE_LESSON", "0").strip().lower() in ("1", "true", "yes", "on")         # 19.10, слово Yaro: урок 1.5 не роздаємо, мітка retush одразу на картку курсу
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
PICK_WIN = int(os.getenv("PICK_WIN", "5400"))   # с: вибір тарифу не раніше ніж за 90 хв до платежу, щоб впізнати серед кількох
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
# 20.10 (слово Yaro): кнопка «Хочу на МК» в каналі більше не показує одразу картку з заявкою.
# Спершу коротке привітання з кнопкою «Дізнатися детальніше»; лише її натиск (mk_open) є кроком цікавості,
# а заявка (mk_want) лишається окремою кнопкою на картці. Так відсіюються випадкові натиски в каналі.
MK_HELLO = (
    "Привіт, це Іра ♥️ Ви натиснули «Хочу на МК» у каналі.\n\n"
    "Майстер-клас індивідуальний: студія, імпульсне світло, ви знімаєте самі, я поруч і виправляю.\n\n"
    "Якщо справді цікаво, тисніть кнопку, розкажу детальніше."
)
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
# Без оплати (PAY_URL порожній, слово Yaro 29.09): бот завершений
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
# Ідея Yaro 15.10: гайд 199 як перший платний крок. GUIDE_PRICE=199 на Render міняє ціну
# всім без деплою (кнопка, картка, звірка суми в банці); GUIDE_OLD_PRICE=900 додає в картку
# «замість 900», лише коли стара ціна більша за чинну.
_G_OLD = _price(os.getenv("GUIDE_OLD_PRICE", ""), 0)
_G_LINE = "Гайд «Світло», " + str(_G) + " грн" + (" замість " + str(_G_OLD) if _G_OLD > _G else "")


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
           "text": (_G_LINE + "\n\n"
                    "Сім років я знімаю зі світлом. Усе, що справді працює, зібрала в один гайд: "
                    "тринадцять моїх робочих схем, до кожної розстановка, налаштування і кадр зі зйомки. "
                    "Доступ залишається назавжди."),
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
# оплату звіряли саме зі зниженою сумою; видається як звичайний курс k12.
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
# 13.10 (слово Yaro: «чи до кнопки «Мої матеріали» можна внизу ще додати кнопку каналу назавжди, щоб вона там
# була»): поруч у тому ж ряду кнопка каналу. Кнопка клавіатури посилання не відкриває: на натискання бот
# відповідає рядком Іри з інлайн-кнопкою в канал (kanal_btn_reply). Підпис «Канал «для своїх»» 17 знаків
# влазить у половину ряду на екрані 360 dp: Roboto 16 dp дає 136 dp при ~152 dp місця (обріже лише на 320 dp).
KANAL_BTN = "Канал «для своїх»"
PERSIST_KB = {"keyboard": [[{"text": "Мої матеріали"}, {"text": KANAL_BTN}]], "resize_keyboard": True,
              "is_persistent": True}
# Версія прапорця: pkb:<id> ставила стара клавіатура лише з «Мої матеріали». Нова має свій прапорець pkb2:<id>,
# тож кожен зі старою отримає нову при наступному зверненні до бота (рядок-носій раз), без розсилки.
PKB_KEY = "pkb2"
PERSIST_METHODS = ("sendMessage", "sendPhoto", "sendDocument", "sendVideo")
# 13.10 (слово Yaro: «для всіх завжди», «завжди на виду»): кнопка в кожного з першого /start.
# Вітання має свою інлайн-кнопку, а повідомлення несе лише одну клавіатуру, тож тоді кнопку
# везе окремий рядок-носій (текст з видачі курсу). Коли якась відповідь апдейту і так без
# своєї клавіатури, кнопка їде на ній, і рядка нема (pkb_finish).
PERSIST_LINE = "Усе куплене завжди під рукою в меню «Мої матеріали»."
_pkb_done = set()    # кому кнопку вже віддано (прапорець pkb:<id> у kv); у памʼяті, щоб не питати базу щоразу

# 403 на відправку людині (заблокувала бота, видалила акаунт, ніколи не починала): kv blocked:<id>, час
# у updated_at (13.10, push1). Розсилки її пропускають, доки вона знову не напише боту (last_seen_at пізніше).
BLOCK_METHODS = ("sendMessage", "sendPhoto", "sendDocument", "sendVideo", "sendMediaGroup", "sendAudio",
                 "sendVoice", "sendAnimation", "sendVideoNote", "sendSticker", "copyMessage", "copyMessages",
                 "forwardMessage")


def mark_blocked(chat_id, why=None):
    """Позначка «заблокували бота» лише для людей (id > 0), не для каналів і груп."""
    try:
        cid = int(chat_id)
    except (TypeError, ValueError):
        return
    if cid <= 0 or not store.ON:
        return
    try:
        store.kv_set("blocked:" + str(cid), (why or "403")[:200])
    except Exception as e:
        log.warning("blocked %s: %s", cid, e)


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
        if j.get("error_code") == 403 and method in BLOCK_METHODS:
            mark_blocked(params.get("chat_id"), j.get("description"))
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
    """Чи людина вже отримала постійну клавіатуру чинної версії: прапорець pkb2:<id> у kv (з 13.10)."""
    if uid in _pkb_done:
        return True
    try:
        v = store.kv_get(PKB_KEY + ":" + str(uid))
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
        store.kv_set(PKB_KEY + ":" + str(uid), "1")
    except Exception as e:
        log.warning("pkb %s: %s", uid, e)


# Відповідь на кнопку каналу: рядок з затвердженого push1 (рядок про канал вибрав Yaro 13.10), без «А також».
# Змінна KANAL_BTN_TEXT на Render перебиває. Посилання: окреме запрошення knopka (рахує вступи з кнопки),
# лише в змінній KANAL_KNOPKA_URL на Render; без неї CHANNEL_URL.
KANAL_BTN_TEXT = (os.getenv("KANAL_BTN_TEXT", "").strip().replace("\\n", "\n")
                  or "Підписуйтесь на мій тг канал, там розповідаю свою історію🫶🏻")
KANAL_KNOPKA_URL = os.getenv("KANAL_KNOPKA_URL", "").strip()


def kanal_btn_url():
    for url in (KANAL_KNOPKA_URL, CHANNEL_URL):
        if url.startswith("https://t.me/"):
            return url
    return "https://t.me/" + (CHANNEL_ID.lstrip("@") or "iryna_rul_photographer")


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


def yaro_account(uid):
    """Акаунт Yaro (14.10): адмін або id з позначкою «акаунт Yaro» у LYUDY_MARKS (читається під час
    виклику: змінну оголошено нижче). Його тести й клацання (ЗАЯВКА, «МК: видано», текст у боті)
    не службові новини для Іри."""
    if not uid:
        return False
    if ADMIN_ID and uid == ADMIN_ID:
        return True
    return "акаунт yaro" in str(LYUDY_MARKS.get(uid, "")).lower()


def _without_ira(ids, target):
    """Одержувачі сповіщення про `target`: про акаунт Yaro Ірі не йдемо (Yaro й далі отримує).
    Бувало тричі за 14.10: тести з акаунта Yaro дійшли Ірі як «Повідомлення в боті від YR…» і ЗАЯВКА."""
    if not (IRA_ID and yaro_account(target)):
        return list(ids)
    kept = [c for c in ids if c != IRA_ID]
    if len(kept) != len(list(ids)):
        log.info("акаунт Yaro %s: Ірі сповіщення не шлемо", target)
    return kept


def _staff_send(ids, text, markup=None, uid=None):
    """Сповіщення персоналу без постійної кнопки, навіть коли пише сам адмін (13.10). Сповіщення про
    одну людину (uid або єдиний «id N» у тексті) несе кнопки «Написати» і «🎁 Подарунок» (тим, хто
    може /do), а reply на нього йде цій людині (14.10). Про акаунт Yaro Ірі не йде (14.10)."""
    target = uid or _one_person(text)
    ids = _without_ira(ids, target)
    person, _tm.person = getattr(_tm, "person", None), None
    try:
        for cid in ids:
            # про себе кнопок не треба (адмін як людина: «ТЕСТ оплати» про нього ж)
            res = send(cid, text, _with_person(markup, target)
                       if target and target != cid and staff_cmd(cid) else markup)
            if target:
                _fb_remember(cid, res, target)
    finally:
        _tm.person = person


def notify_lead(text, uid=None):
    _staff_send(LEAD_IDS, text, uid=uid)


def notify(text, markup=None, uid=None):
    _staff_send(NOTIFY_IDS, text, markup, uid)


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
    for cid in _without_ira(staff_ids(), uid):
        if head:
            _fb_remember(cid, send(cid, "Від " + who(u) + " (" + tag + ")"
                                   + (":\n" + cap if cap else "")
                                   + "\nВідповідь: reply на це або на файл нижче.",
                                   _with_person(None, uid) if staff_cmd(cid) else None), uid)
        _fb_remember(cid, api("forwardMessage", chat_id=cid, from_chat_id=chat_id,
                              message_id=m.get("message_id")), uid)


def fb_target(rep, uid=None):
    """Кому адресована відповідь: з пам'яті, з кнопки «Написати» (napys:<id>), з forward_origin або
    з єдиного рядка «id N» у тексті. На власне повідомлення персоналу (не бота) лише з пам'яті:
    чужий «id N» у своєму тексті чи переслане від друга людиною не вважаємо."""
    if not rep:
        return None
    t = _fb_map.get((rep.get("_chat"), rep.get("message_id")))
    if t:
        return t
    if uid and (rep.get("from") or {}).get("id") == uid:
        return None
    for row in (rep.get("reply_markup") or {}).get("inline_keyboard") or []:
        for b in row:
            cd = b.get("callback_data") or ""
            if cd.startswith("napys:") and cd[6:].isdigit():
                return int(cd[6:])
    fo = rep.get("forward_origin") or {}
    su = fo.get("sender_user") or {}
    if su.get("id"):
        return su["id"]
    return _one_person(rep.get("text") or rep.get("caption") or "")


def staff_reply(m, chat_id):
    """Reply персоналу на переслане/сповіщення -> людині (сумісна обгортка над staff_route).
    True, якщо оброблено."""
    if not m.get("reply_to_message"):
        return False
    return staff_route(m, chat_id, (m.get("from") or {}).get("id"))


# ---------- відповідь людині будь-чим (14.10) ----------
# Слово Yaro 14.10: «щоб можна було будь-що, будь-яке повідомлення легко людині надіслати без
# переписування всього бота і передеплоювання». Три дороги, одна доставка і один журнал:
#  1) reply персоналу на будь-яке сповіщення про людину (текст, фото, альбом, файл, голосове, кружок, стікер);
#  2) /do <id> або кнопка «Написати» під сповіщенням: наступне повідомлення (будь-яке) піде цій людині;
#  3) з ПК: POST /nadislaty/<секрет> (скрипт projects/iryna/bot/nadislaty.py у cowork).
# Людина отримує копію без «переслано»; персонал коротке «Пішло: …» чи «Не пішло: …» reply-ем на своє.
# Кожна відправка = подія staff_reply {by, via, type, text}: /events її показує, push1 рахує «бот писав».

BOT_ID = int(TOKEN.split(":")[0]) if TOKEN.split(":")[0].isdigit() else 0
DO_TTL = 3600             # секунд живе режим /do без повідомлення
ALBUM_QUIET = 1.5         # секунд тиші, після яких альбом персоналу йде людині одним copyMessages
ALBUM_LATE_S = 60         # пізні елементи вже відправленого альбому йдуть тій самій людині
IRA_OWN = ("Прийняла ♥️",)     # reply Іри на ці відповіді бота = її матеріали, не «нема кому»
_do = {}                  # хто з персоналу -> (кому, коли); None = перевірено, режиму нема
_alb = {}                 # (чат, media_group_id) -> альбом персоналу, що збирається
_alb_done = {}            # (чат, media_group_id) -> (кому, як, коли) для пізніх елементів
_alb_lock = threading.Lock()
_alb_tick = threading.Event()      # чекаємо Event.wait-ом: тести підміняють time.sleep
_alb_spawn = [None]       # тести: свій запуск флашу замість bg


def staff_cmd(uid):
    """Хто може /do, /skasuvaty і кнопки «Написати»/«Подарунок»: NOTIFY_IDS і адмін."""
    return bool(uid) and (uid in NOTIFY_IDS or uid == ADMIN_ID)


def person_rows(uid):
    return [[{"text": "Написати", "callback_data": "napys:%d" % uid},
             {"text": "🎁 Подарунок", "callback_data": "podar:%d" % uid}]]


def _one_person(text):
    """Єдиний різний id у тексті; кілька різних = None (не вгадуємо, кому)."""
    ids = {int(x) for x in _ID_RE.findall(text or "")}
    return ids.pop() if len(ids) == 1 else None


def _with_person(markup, uid):
    """Рядок «Написати | 🎁 Подарунок» у кінець інлайн-клавіатури (перші кнопки лишаються на місці)."""
    if markup and "inline_keyboard" not in markup:
        return markup
    return {"inline_keyboard": list((markup or {}).get("inline_keyboard") or []) + person_rows(uid)}


def person_name(uid, ask=True):
    """«Ім'я, @нік, id N» з бази; нема в базі і ask: getChat. Telegram людину не знає = None."""
    u = None
    try:
        u = store.get_user(uid)
    except Exception as e:
        log.warning("person_name %s: %s", uid, e)
    if not u and ask:
        r = api_raw("getChat", chat_id=uid)
        u = r.get("result") if r.get("ok") and isinstance(r.get("result"), dict) else None
    if not u:
        return None
    return who({"id": uid, "username": u.get("username"),
                "first_name": u.get("first_name"), "last_name": u.get("last_name")})


def _staff_say(chat_id, text, reply_to=None, target=None):
    """Коротка відповідь персоналу reply-ем на його повідомлення, без постійної кнопки;
    з target reply на неї теж іде цій людині."""
    person, _tm.person = getattr(_tm, "person", None), None
    try:
        res = api("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True,
                  reply_parameters={"message_id": reply_to, "allow_sending_without_reply": True}
                  if reply_to else None)
    finally:
        _tm.person = person
    if target:
        _fb_remember(chat_id, res, target)
    return res


def _send_err(r):
    d = str(r.get("description") or "")
    if r.get("error_code") == 403:
        return "людина заблокувала бота"
    if "chat not found" in d.lower() or "can't initiate" in d.lower():
        return "людина ще не писала боту"
    return d or "Telegram не відповів"


def msg_kind(m):
    return extract_file(m)[0] or ("текст" if m.get("text") else "інше")


def _log_sent(target, by, via, kind, text):
    """13.10: відповідь персоналу теж «бот писав людині» (push1 не шле тим, кому писали за 24 год)."""
    try:
        store.log_event(target, "staff_reply", {"by": by, "via": via, "type": kind, "text": (text or "")[:300]})
    except Exception as e:
        log.warning("staff_reply подія %s: %s", target, e)


def copy_to_person(chat_id, mids, target, by, via, kind, text, reply_to=None):
    """Копія повідомлень персоналу людині (без «переслано»), подія і «Пішло»/«Не пішло». True = дійшло."""
    mids = sorted(mids)
    if len(mids) == 1:
        r = api_raw("copyMessage", chat_id=target, from_chat_id=chat_id, message_id=mids[0])
    else:
        r = api_raw("copyMessages", chat_id=target, from_chat_id=chat_id, message_ids=mids)
    name = person_name(target) or "id %s" % target
    if not r.get("ok"):
        log.warning("персонал -> %s (%s): %s", target, via, r.get("description"))
        _staff_say(chat_id, "Не пішло: " + name + ": " + _send_err(r), reply_to)
        return False
    _log_sent(target, by, via, kind, text)
    for mid in mids:
        _fb_remember(chat_id, {"message_id": mid}, target)     # reply на своє відправлене = тій самій людині
    _staff_say(chat_id, "Пішло: " + name, reply_to, target)
    return True


def do_get(by):
    """Режим /do цього персоналу: (кому або None, чи сплив). Сам режим не знімає."""
    v = _do.get(by, False)
    if v is False:
        v = None
        if store.ON:
            try:
                t, _, ts = (store.kv_get("do:%s" % by) or "").partition(":")
                v = (int(t), float(ts)) if t.isdigit() else None
            except Exception as e:
                log.warning("do_get %s: %s", by, e)
        _do[by] = v
    if not v:
        return None, False
    if time.time() - v[1] > DO_TTL:
        return None, True
    return v[0], False


def do_set(by, target):
    now = time.time()
    _do[by] = (target, now)
    if store.ON:
        try:
            store.kv_set("do:%s" % by, "%s:%d" % (target, now))
        except Exception as e:
            log.warning("do_set %s: %s", by, e)


def do_clear(by):
    _do[by] = None
    if store.ON:
        try:
            store.kv_set("do:%s" % by, "")
        except Exception as e:
            log.warning("do_clear %s: %s", by, e)


def do_start(chat_id, by, target, reply_to=None):
    """Режим /do: наступне повідомлення персоналу піде людині. Telegram її не знає = відмова."""
    name = person_name(target)
    if not name:
        _staff_say(chat_id, "Не можу: id %s боту невідомий (людина ще не писала боту)." % target, reply_to)
        return False
    do_set(by, target)
    _staff_say(chat_id, "Наступне ваше повідомлення піде: " + name
               + "\nБудь-що: текст, фото, альбом, файл, голосове, кружок, стікер. Скасувати: /skasuvaty",
               reply_to, target)
    return True


def podarunok_staff(chat_id, target, reply_to=None):
    """/podarunok <id> і кнопка «🎁 Подарунок»: той самий give_gift з GIFT_HAND (раз назавжди, kv gift:<id>)."""
    name = person_name(target, ask=False) or who({"id": target})
    try:
        ok = give_gift(target, GIFT_HAND)
    except Exception:
        log.exception("podarunok %s", target)
        ok = False
    if ok:
        _staff_say(chat_id, "Подарунок (три схеми світла) пішов: " + name, reply_to)
    else:
        _staff_say(chat_id, "Не пішло: " + name + ". Схеми вже видані, подарунок уже йшов (заявка gift), "
                   "або нема файла магніту / людина заблокувала бота. Дивись /lyudy.", reply_to)
    return ok


def _from_bot(rep):
    f = rep.get("from") or {}
    return bool(f.get("is_bot") or (BOT_ID and f.get("id") == BOT_ID))


def _route(m, chat_id, uid):
    """(кому, як: reply|do, чому ні). Усе None = повідомлення не людині (матеріали Іри, адмін як людина)."""
    text = (m.get("text") or m.get("caption") or "").strip()
    if text in ("Мої матеріали", KANAL_BTN):
        return None, None, None            # кнопки постійної клавіатури адміна людям не шлемо
    rep = m.get("reply_to_message")
    if rep:
        t = fb_target(dict(rep, _chat=chat_id), uid)
        if t:
            if t in staff_ids() and t != uid:
                return None, None, None    # як до 14.10: відповідь про когось із персоналу не пересилаємо
            return t, "reply", None
        if _from_bot(rep) and (rep.get("text") or "") not in IRA_OWN + (IRA_HELLO,):
            many = len(set(_ID_RE.findall(rep.get("text") or rep.get("caption") or ""))) > 1
            return None, None, (("у цьому повідомленні кілька людей, не знаю кому" if many
                                 else "не бачу, кому це") + ". Напишіть /do <id> і надішліть ще раз.")
    if staff_cmd(uid):
        t, expired = do_get(uid)
        if t:
            return t, "do", None
        if expired:
            return None, "do", "режим /do сплив (година без повідомлення). Напишіть /do <id> ще раз."
    return None, None, None


def staff_route(m, chat_id, uid):
    """Повідомлення персоналу -> людині, якщо є адреса: reply на сповіщення про неї, на «Пішло» чи
    картку /do, або режим /do. True = оброблено (пішло, не пішло чи пояснили чому);
    False = це не людині, далі звичайна обробка."""
    target, via, why = _route(m, chat_id, uid)
    if m.get("media_group_id"):
        return _album_add(m, chat_id, uid, target, via, why)
    if via == "do":
        do_clear(uid)                      # режим на одне повідомлення (і сплилий теж знімаємо)
    if why:
        _staff_say(chat_id, "Не пішло: " + why, m.get("message_id"))
        return True
    if not target:
        return False
    copy_to_person(chat_id, [m["message_id"]], target, uid, via, msg_kind(m),
                   m.get("text") or m.get("caption"), m.get("message_id"))
    return True


def _album_add(m, chat_id, uid, target, via, why):
    """Елемент альбому персоналу: збираємо (Telegram шле альбом окремими апдейтами, пул обробляє їх
    паралельно), після ALBUM_QUIET тиші весь альбом іде людині одним copyMessages і одним «Пішло»."""
    key = (chat_id, str(m.get("media_group_id")))
    spawn, late = False, None
    with _alb_lock:
        a = _alb.get(key)
        if a is None and key in _alb_done:
            late = _alb_done[key]
        elif a is None and not (target or why):
            return False                   # альбом не людині
        else:
            if a is None:
                a = _alb[key] = {"mids": [], "kinds": [], "text": "", "by": uid, "target": None,
                                 "via": None, "why": None, "do": False, "t": 0.0}
                spawn = True
            a["mids"].append(m["message_id"])
            a["kinds"].append(msg_kind(m))
            a["text"] = a["text"] or m.get("caption") or ""
            if target and not a["target"]:
                a["target"], a["via"] = target, via
            a["why"] = a["why"] or why
            a["do"] = a["do"] or via == "do"
            a["t"] = time.time()
    if late is not None:
        if late[0]:
            copy_to_person(chat_id, [m["message_id"]], late[0], uid, late[1], msg_kind(m),
                           m.get("caption"), m.get("message_id"))
        return True
    if spawn:
        (_alb_spawn[0] or bg)(_album_wait, key)
    return True


def _album_wait(key):
    while True:
        with _alb_lock:
            a = _alb.get(key)
            if a is None:
                return
            left = a["t"] + ALBUM_QUIET - time.time()
        if left <= 0:
            break
        _alb_tick.wait(min(left, 0.5))
    album_flush(key)


def album_flush(key):
    now = time.time()
    with _alb_lock:
        a = _alb.pop(key, None)
        if a is None:
            return
        for k in [k for k, v in _alb_done.items() if now - v[2] > ALBUM_LATE_S]:
            _alb_done.pop(k, None)
        _alb_done[key] = (a["target"], a["via"] or "reply", now)
    chat_id, mids = key[0], sorted(a["mids"])
    if a["do"]:
        do_clear(a["by"])
    if a["target"]:
        counts = {}
        for k in a["kinds"]:
            counts[k] = counts.get(k, 0) + 1
        kind = "альбом: " + ", ".join("%s×%d" % kv for kv in counts.items())
        copy_to_person(chat_id, mids, a["target"], a["by"], a["via"], kind, a["text"], mids[0])
    elif a["why"]:
        _staff_say(chat_id, "Не пішло: " + a["why"], mids[0])


def album_flush_all():
    """Тести і зупинка: усі зібрані альбоми зараз."""
    for key in list(_alb):
        album_flush(key)


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


def pick_product(chat_id, uid, u, data, gate=True):
    """Картка товару з кодом платежу і кнопкою оплати (кнопка тарифу і /start kurs).
    gate: ворота ціни (п.4-6): холодній людині ретуші замість картки курсу йде запрошення Т9;
    явні теплі входи (/start kurs, kurs10, /kurs, кнопка «Розкажіть про курс») кличуть з gate=False."""
    # 08.10, слово Yaro: знижка 10 % поки для всіх, кожен бачить її як особисту.
    if data == "k12" and COURSE_BUNDLE_ONLY:
        data = "k12z"
    t = PRODUCTS[data]
    if gate and t["product"] == "course" and cold(uid):
        send_zapr(chat_id, uid)
        return
    code = order_code(uid, data)
    store.add_purchase(uid, t["product"], tier=data, order_code=code,
                       amount_uah=osobysta_tsina(uid, data) or t["uah"])
    store.log_event(uid, "tier_pick", {"tier": data, "code": code})
    # 19.10, слово Yaro: людині нічого вписувати не треба, оплату бот звіряє сам; без PAY_URL код лишається
    body = t["text"] if PAY_URL else t["text"] + "\n\nПризначення платежу, впишіть його дослівно:\n" + code
    if PAY_URL:
        body += ("\n\nПісля оплати курс відкриється тут, зазвичай протягом кількох хвилин."
                 if t["product"] == "course" else
                 "\n\nПісля оплати файл прийде сюди, зазвичай протягом кількох хвилин.")
    send(chat_id, body, pay_kb(data, uid))
    if lead_once(uid, "zayavka:" + data):
        notify("ЗАЯВКА: " + t["name"] + "\n" + who(u) + "\nКод: " + code,
               give_kb(uid, data), uid=uid)


def mk_kb():
    return {"inline_keyboard": [[{"text": "Хочу на майстер-клас", "callback_data": "mk:want"}]]}


def mk_hello_kb():
    return {"inline_keyboard": [[{"text": "Дізнатися детальніше", "callback_data": "mk"}]]}


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


# Лід-магніт ретуші (MAGNIT-RETUSH-2026-10-08.md, тексти дослівно): без ціни, лише один урок.
# 20.10: урок 1.3 «Маски: волосся і фон» (Camera Raw) замість 1.5 «Чистка шкіри»; 7 хвилин замість 12.
_HELLO_AUTO = (
    "Привіт, це Ірина Руль ♥️\n\n"
    "Тут мій урок «Маски: волосся і фон» з курсу ретуші, цілком, 7 хвилин.\n"
    "Маски в Camera Raw, якими виділяю волосся і фон, і лайфхак для каталогу.\n\n"
    "Тисніть кнопку, урок відкриється в моєму кабінеті курсів.\n\n"
    "А після уроку на вас чекає маленький подарунок від мене 🎁"
)
_GIFT_DONE_AUTO = (
    "Ви додивились♥️ Як і обіцяла, маленький подарунок: «Три схеми світла з одного сетапу», "
    "три різні картинки за одну зйомку без докупки обладнання. Файл нижче\n\n"
    "Напишіть, як вам урок? Мені важливо♥️"
)
GIFT_LATE = (
    "Урок чекає на вас♥️ 7 хвилин, коли буде зручно. А подарунок віддаю вже зараз: "
    "«Три схеми світла з одного сетапу», файл нижче"
)
# Подарунок лише за підписку (GIFT_FOR_SUB, п.1): тексти Т1-Т5 з VORONKA-2026-10.md дослівно, чернетка для Іри.
_HELLO_SUB = (                              # 16.10: одна кнопка «Відкрити урок», без каналу, без слова «курс», без ціни
    "Привіт, це Ірина Руль ♥️\n\n"
    "Тут мій урок «Маски: волосся і фон», цілком, 7 хвилин. "
    "Маски в Camera Raw, якими виділяю волосся і фон, і лайфхак для каталогу.\n\n"
    "Тисніть «Відкрити урок», він відкриється в моєму кабінеті. "
    "А після уроку на вас чекає подарунок: три схеми світла."
)
SUB_NO = (                                  # Т2: натиснула, а в каналі її нема
    "Поки не бачу вас у каналі ♥️ Натисніть «Канал «для своїх»», підпишіться і поверніться сюди, "
    "ще раз «Я підписалась». Файл прийде одразу."
)
GIFT_SUB = (                                # Т3: підписка підтверджена, файл нижче
    "Дякую, що ви з нами ♥️ Тримайте подарунок: «Три схеми світла з одного сетапу». "
    "Три різні картинки за одну зйомку, без докупки обладнання. Спробуйте на найближчій зйомці."
)
SUB_ALREADY = "Подарунок уже у вас ♥️ Файл надсилала вище в цьому чаті."
SUB_UNKNOWN = "Не можу зараз перевірити підписку ♥️ Подивлюсь сама і надішлю файл."   # ризик (а): бот не адмін каналу
GIFT_DONE_ASK = "Ви додивились ♥️ Напишіть, як вам урок? Мені важливо."              # Т4, подарунок уже був
_GIFT_DONE_SUB = GIFT_DONE_ASK + "\n\nПодарунок, як обіцяла: «Три схеми світла з одного сетапу», файл нижче"
GIFT_DONE_NOSUB = (                         # 16.10: done → текст + Канал/«Я підписалась»; файл лише після sub:check
    "Ви додивились ♥️ Подарунок «Три схеми світла» віддаю підписникам каналу «для своїх»: "
    "там бекстейдж і до/після зі зйомок."
)
GIFT_REMIND = (                             # Т5: день 1, непідписаній, один раз
    "Доброго дня ♥️ Подарунок досі чекає: «Три схеми світла з одного сетапу». Підпишіться на канал "
    "«для своїх» і натисніть «Я підписалась», файл прийде сюди.\n\n"
    "А урок про маски, якщо ще не дивились, чекає за кнопкою. Це 7 хвилин, коли буде зручно."
)
RETUSH_MAGNET_HELLO = _HELLO_SUB if GIFT_FOR_SUB else _HELLO_AUTO
GIFT_DONE = _GIFT_DONE_SUB if GIFT_FOR_SUB else _GIFT_DONE_AUTO
TOUCH_D1_LESSON = "Урок чекає на вас ♥️ 7 хвилин, коли буде зручно"       # Д1, ще не додивилась
TOUCH_D2_HAJD = ("Три схеми у вас. Усі тринадцять, з розстановкою і кадром, у гайді «Світло», "
                 "%d грн, доступ назавжди.")                                  # Д2, ціна з GUIDE_PRICE
# Ворота ціни (п.4-6): Т9, запрошення без ціни; ціна лише після кнопки «Розкажіть про курс».
ZAPR_TEXT = (
    "Хочу розповісти про свій курс ретуші ♥️ Він для тих, кого лякає Photoshop, а гарні кадри хочеться. "
    "18 відео, близько 135 хвилин, і файли для практики з моїми пресетами. "
    "Якщо цікаво, натисніть «Розкажіть про курс»."
)
GIFT_HAND = (
    "Маленький подарунок від мене♥️\n"
    "«Три схеми світла з одного сетапу», файл нижче"
)                                           # ручна видача /podarunok (слово Yaro 14.10, Альона)
GIFT_FROM_H, GIFT_TO_H = 10, 20            # лише денні години за Києвом
GIFT_AFTER_H = 24                           # через скільки годин після входу без done
GIFT_SINCE = os.getenv("GIFT_SINCE", "2026-10-12T12:00:00+00:00")   # раніше зайшлі не чіпаємо
RETUSH_LESSON_PART = "1.3"   # 20.10, слово Yaro: даємо урок з масками в Camera Raw, який радила Іра (08.10, 15.10); до того 1.5

# 16.10: два входи на один шлях, ?start=svitlo (реклама) і ?start=profil (шапка Instagram):
# привіт про три схеми світла, «Канал» + «Я підписалась», файл після живого sub:check (без уроку ретуші і ціни).
SVITLO_TAGS = ("svitlo", "profil", "storis", "svit", "shema2", "koment", "mc", "mck")   # 21.10: mc = ManyChat ключове слово в Direct, mck = ManyChat коментар   # 21.10: koment = приватна відповідь на коментар «схема» під рілсом   # 18.10: storis = сторіз Іри, svit = реклама на світ без України; 21.10: shema2 = реклама UA з рілсом «Чорний фон»
# Тексти з projects/iryna/kontent/2026-10-16-svitlo-statyka/TEKST.md п.5 дослівно (копірайтер, Іра пише «це Іра»).
SVITLO_HELLO = (
    "Привіт, це Іра ♥️\n"
    "Час на студії обмежений, а картинки потрібні різні, тому тут моя добірка «Три схеми світла з одного сетапу»: "
    "три різні картинки за одну зйомку.\n"
    "Віддаю її підписникам каналу «для своїх». Підпишіться, натисніть «Я підписалась», і файл прийде сюди."
)
PROFIL_HELLO = (
    "Привіт, це Іра ♥️\n"
    "Ви прийшли з мого профілю, тут добірка «Три схеми світла з одного сетапу»: три різні картинки за одну зйомку.\n"
    "Віддаю її підписникам каналу «для своїх». Підпишіться, натисніть «Я підписалась», і файл прийде сюди."
)
SVITLO_HELLOS = {"svitlo": SVITLO_HELLO, "profil": PROFIL_HELLO, "storis": SVITLO_HELLO, "svit": SVITLO_HELLO, "shema2": SVITLO_HELLO, "koment": SVITLO_HELLO, "mc": SVITLO_HELLO, "mck": SVITLO_HELLO}
# 17.10: реклама гайда (креатив Іри 299), ?start=hajd299 одразу дає картку гайда з тарифами, як слово «гайд»;
# окрема мітка, щоб у /lyudy порівняти з svitlo (вхід, канал, покупка)
HAJD_TAG = "hajd299"
# 21.10 (Yaro: «пресети прикольна штука… придумаєш магніт і відос під нього»): магніт ретуші, пресет кольору Іри
# з рілса «Один клік». ManyChat слово «ПРЕСЕТ» → ?start=preset. Файл одразу, без замка каналу («простота продає»).
PRESET_TAG = "preset"
PRESET_FILE = "static/Iryna-Rul-Kolir-1.xmp"
PRESET_HELLO = (
    "Привіт, це Іра ♥️\n"
    "Мій пресет «Колір 1» для Lightroom і Camera Raw: той колір, що у відео, одним кліком. Файл нижче.\n\n"
    "Як поставити: Lightroom → Presets → три крапки → Import Presets → цей файл.\n"
    "Camera Raw → вкладка Presets → три крапки → Import Profiles & Presets."
)
PRESET_AFTER = (
    "Пресет дає колір. Шкіру, обʼєм і світло на цих кадрах я роблю руками, саме це розбираю в курсі ретуші.\n\n"
    "У каналі «Iryna Rul | для своїх» показую «до/після» з кожної зйомки."
)
SVITLO_REMIND = (                           # Д1 для svitlo/profil без файла: без уроку
    "Доброго дня ♥️ Три схеми світла чекають: підпишіться на канал «для своїх» і натисніть "
    "«Я підписалась», файл прийде сюди."
)


def svitlo_tag(uid):
    """Мітка svitlo/profil з бази (source_tag), інакше ''."""
    try:
        t = ((store.get_user(uid) or {}).get("source_tag") or "").strip().lower()
    except Exception:
        return ""
    return t if t in SVITLO_TAGS else ""


def svitlo_channel_url(tag):
    """Окреме запрошення на мітку (CHANNEL_URL_SVITLO / CHANNEL_URL_PROFIL, щоб бачити в каналі, звідки прийшли),
    інакше CHANNEL_URL."""
    return os.getenv("CHANNEL_URL_" + tag.upper(), "").strip() or CHANNEL_URL


def svitlo_kb(tag="svitlo"):
    url = svitlo_channel_url(tag)
    rows = [[{"text": "Канал «для своїх»", "url": url}]] if url else []
    return {"inline_keyboard": rows + [[{"text": "Я підписалась", "callback_data": "sub:check"}]]}


def retush_lesson_url():
    """Кабінет одразу на уроці 1.5 (кабінет читає ?p= і відкриває частину за номером)."""
    return kabinet_mist.URL + "/?p=" + RETUSH_LESSON_PART if kabinet_mist.URL else ""


def retush_channel_rows():
    """Кнопка каналу для людей ретуші: окреме запрошення CHANNEL_URL_RETUSH (п.10), інакше CHANNEL_URL."""
    url = CHANNEL_URL_RETUSH or CHANNEL_URL
    return [[{"text": "Канал «для своїх»", "url": url}]] if url else []


def sub_kb(lesson=False):
    """«Канал» і «Я підписалась» (п.1); lesson=True додає зверху «Відкрити урок» (Т5 тим, хто без done)."""
    url = retush_lesson_url()
    rows = [[{"text": "Відкрити урок", "web_app": {"url": url}}]] if lesson and url else []
    return {"inline_keyboard": rows + retush_channel_rows()
            + [[{"text": "Я підписалась", "callback_data": "sub:check"}]]}


def retush_magnet_kb():
    """Mini App кнопка: Telegram сам передає підписаний initData, вхід без паролів.
    Без KABINET_URL кнопки нема (тоді лише канал), щоб не слати в нікуди.
    З GIFT_FOR_SUB (16.10) лише «Відкрити урок»."""
    url = retush_lesson_url()
    rows = [[{"text": "Відкрити урок", "web_app": {"url": url}}]] if url else []
    if GIFT_FOR_SUB:
        return {"inline_keyboard": rows}           # 16.10: лише «Відкрити урок»; канал і «Я підписалась» з'являються на done
    return {"inline_keyboard": rows + channel_rows()}


def zapr_kb():
    return {"inline_keyboard": [[{"text": "Розкажіть про курс", "callback_data": "zapr:open"}]]
            + retush_channel_rows()}


def cold(uid):
    """Холодна людина ретуші (п.4): прийшла за міткою retush* (реклама, партнери), ще не тиснула
    «Розкажіть про курс» (kv zapr:<id>) і нічого не купила. Їй ціну курсу не показуємо.
    Персонал не виняток: Yaro після /nova бачить те саме, що людина з реклами."""
    if not PRICE_GATE or not uid:
        return False
    try:
        if store.kv_get("zapr:" + str(uid)):
            return False
        tag = (store.get_user(uid) or {}).get("source_tag") or ""
        if not tag.startswith("retush"):
            return False
        return not owned_keys(uid, real=True)
    except Exception:
        log.exception("cold %s", uid)
        return False


def send_zapr(chat_id, uid):
    """Т9 замість картки з ціною; подія gate, щоб бачити, скільки холодних просили курс самі."""
    store.log_event(uid, "gate")
    send(chat_id, ZAPR_TEXT, zapr_kb())


def kanal_member_fresh(uid):
    """getChatMember без кешу: щойно підписана не має отримати вчорашнє «ні»."""
    _kanal_cache.pop(uid, None)
    return kanal_member(uid)


def _sub_kb_for(uid):
    """Клавіатура «Канал» + «Я підписалась»: для svitlo/profil звичайний канал, для решти sub_kb()."""
    t = svitlo_tag(uid)
    return svitlo_kb(t) if t else sub_kb()


def sub_check(chat_id, uid, u):
    """Кнопка «Я підписалась» (п.1). В каналі: подарунок раз назавжди (give_gift) і подія sub_ok.
    Нема: Т2 з тими самими кнопками. Невідомо (бот не адмін каналу, Telegram мовчить): людині
    «подивлюсь сама», персоналу сповіщення з кнопкою «🎁 Подарунок» (ризик (а) у VORONKA)."""
    inn, why = kanal_member_fresh(uid)
    store.log_event(uid, "sub_check", {"in": inn, "why": why})
    if inn:
        if store.kv_claim("sub_ok:" + str(uid)):
            store.log_event(uid, "sub_ok")
        if not give_gift(uid, GIFT_SUB):
            send(chat_id, SUB_ALREADY)
        return
    if inn is False:
        send(chat_id, SUB_NO, _sub_kb_for(uid))
        return
    send(chat_id, SUB_UNKNOWN, _sub_kb_for(uid))
    if lead_once(uid, "sub_unknown"):
        notify("Підписку не перевірити (" + why + "): " + who(u),
               {"inline_keyboard": [[{"text": "🎁 Подарунок", "callback_data": "podar:%d" % uid}]]}, uid=uid)


def lesson_done_gift(uid, name):
    """done уроку 1.5 з GIFT_FOR_SUB (16.10): файла не шлемо ніколи, лише текст про подарунок і кнопки
    «Канал» + «Я підписалась» (файл після sub:check з живою перевіркою). Хто вже має файл: лише питання про урок."""
    if store.kv_get("gift:" + str(uid)) or (store.get_user(uid) or {}).get("got_magnet_at"):
        send(uid, GIFT_DONE_ASK)
        return
    send(uid, GIFT_DONE_NOSUB, sub_kb())


def osobysta_tsina(uid, key):
    """Особиста ціна курсу (19.10, слово Yaro): /tsina кладе kv tsina:<id>; для k12/k12z важить більше за PRODUCTS."""
    if key not in ("k12", "k12z") or not uid:
        return None
    try:
        v = store.kv_get("tsina:" + str(uid))
        return int(v) if v else None
    except Exception:
        return None


def pay_url(uid, key):
    """Персональне посилання на оплату (Mono «За посиланням», картка Іри): сума і код підставлені
    (?a=сума&t=коментар, є Apple Pay / Google Pay). Код до виписки не доходить, звірка за сумою в handle_tx."""
    if not PAY_URL:
        return ""
    sep = "&" if "?" in PAY_URL else "?"
    return PAY_URL + sep + urlencode({"a": osobysta_tsina(uid, key) or PRODUCTS[key]["uah"],
                                      "t": order_code(uid, key)})


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


def give_preset(chat_id):
    """21.10: магніт ретуші. Привіт, файл пресету з репозиторію, далі місток до курсу (картка магніту, кнопки як після схем)."""
    send(chat_id, PRESET_HELLO)
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), PRESET_FILE), "rb") as f:
            blob = f.read()
    except Exception as e:
        log.warning("preset file: %s", e)
        blob = None
    if not blob or not send_file(chat_id, "Iryna-Rul-Kolir-1.xmp", blob, caption="Iryna Rul · Колір 1 (.xmp)"):
        send(chat_id, "Файл тимчасово недоступний, напишіть Ірині в дірект ♥️")
        return
    send_card(chat_id, CARD_MAGNIT, PRESET_AFTER, after_kb())


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
    if GIFT_FOR_SUB:
        return 0                           # 16.10: автовидачі нема, дотики Д1/Д2 у touch_run
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


TOUCH_D1 = (20, 36)      # годин після входу: нижня межа ~20 год; верхня 36, щоб ніч не з'їла вікно (10:00-20:00 Київ)
TOUCH_D2 = (44, 60)


def _touch_ok(uid):
    """Спільні пропуски дотику: купила (у запиті), 403 (у запиті), стоп-слово."""
    try:
        return not PUSH_STOP_RE.search(store.user_texts(uid) or "")
    except Exception:
        log.exception("touch stop %s", uid)
        return False


def touch_run(now=None):
    """Дотики Д1 і Д2 замість автовидачі (16.10, мудрець). Раз на 10 хв, лише 10:00-20:00 Київ,
    по одному на людину на крок (kv touch_d1:/touch_d2:), персонал і GIFT_SINCE пропускаємо.
    Д1: без done, урок чекає (кнопка «Відкрити урок»); done без подарунка: Т5 (канал, «Я підписалась»).
    Д2: подарунок вже є, гайда нема: «Гайд, N грн» (callback guide, подія hajd199, kv hajd199:)."""
    if not GIFT_FOR_SUB:
        return 0
    now = now or datetime.now(timezone.utc)
    if not (GIFT_FROM_H <= kyiv_hour(now) < GIFT_TO_H):
        return 0
    skip = [i for i in [ADMIN_ID, IRA_ID] + NOTIFY_IDS + LEAD_IDS if i]
    n = 0
    for uid, got in store.touch_candidates(GIFT_SINCE, TOUCH_D1[0], TOUCH_D1[1], skip, "touch_d1:") or []:
        try:
            if owned_keys(uid, real=True) or not _touch_ok(uid):
                continue
            stag = svitlo_tag(uid)
            if stag:                                       # svitlo/profil: уроку нема, лише нагадування про файл
                if got or store.kv_get("gift:" + str(uid)) or not store.kv_claim("touch_d1:" + str(uid)):
                    continue
                ok = send(uid, SVITLO_REMIND, svitlo_kb(stag))
                store.log_event(uid, "touch", {"step": "d1", "tag": stag, "ok": bool(ok)})
                n += 1 if ok else 0
                continue
            done = store.kv_get("kp:%s:%s:done" % (uid, RETUSH_LESSON_PART))
            has_gift = bool(got or store.kv_get("gift:" + str(uid)))
            if done and has_gift:
                continue                                   # додивилась і подарунок має: Д1 нічого
            if not done and not FREE_LESSON:
                continue                                   # 19.10: урок закрито, кликати дивитись нема куди
            if not store.kv_claim("touch_d1:" + str(uid)):
                continue
            if done:
                ok = send(uid, GIFT_REMIND, sub_kb())
            else:
                url = retush_lesson_url()
                kb = {"inline_keyboard": [[{"text": "Відкрити урок", "web_app": {"url": url}}]]} if url else None
                ok = send(uid, TOUCH_D1_LESSON, kb)
            store.log_event(uid, "touch", {"step": "d1", "done": bool(done), "ok": bool(ok)})
            n += 1 if ok else 0
        except Exception:
            log.exception("touch_d1 %s", uid)
    for uid, _got in store.touch_candidates(GIFT_SINCE, TOUCH_D2[0], TOUCH_D2[1], skip, "touch_d2:", with_gift=True) or []:
        try:
            if owned_keys(uid, real=True) or store.kv_get("hajd199:" + str(uid)) or not _touch_ok(uid):
                continue
            if not store.kv_claim("touch_d2:" + str(uid)):
                continue
            kb = {"inline_keyboard": [[{"text": TIERS["t1"]["btn"], "callback_data": "guide"}]]}
            ok = send(uid, TOUCH_D2_HAJD % _G, kb)
            if ok:
                store.kv_set("hajd199:" + str(uid), "touch_d2")
            store.log_event(uid, "hajd199", {"via": "touch_d2", "ok": bool(ok)})
            store.log_event(uid, "touch", {"step": "d2", "ok": bool(ok)})
            n += 1 if ok else 0
        except Exception:
            log.exception("touch_d2 %s", uid)
    return n


def gift_loop():
    STOP.wait(120)
    while not STOP.wait(600):
        store.session_begin()
        try:
            gift_late_run()          # з GIFT_FOR_SUB нічого не робить (16.10)
            touch_run()
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
    if courses_sale():                    # 17.10: канал без умов, покупцеві й так цікаво
        send(uid, NEXT_AFTER_GUIDE, {"inline_keyboard": retush_kb_one()["inline_keyboard"] + channel_rows()})
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
               + str(sent) + " з " + str(total) + " файлів.", uid=uid)
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
    kb = None
    if kabinet_mist.URL:
        # 19.10, слово Yaro: покупниця шукала відео серед файлів практики, тож одразу кажемо, де відео
        lines[1:1] = ["Відео всіх уроків у моєму кабінеті: синя кнопка «Кабінет» зліва внизу або кнопка під цим "
                      "повідомленням. Файли в чаті це практика, їх відкривайте на комп'ютері у Photoshop.", ""]
        kb = {"inline_keyboard": [[{"text": "Відкрити кабінет", "web_app": {"url": kabinet_mist.URL + "/"}}]]}
    for k in keys:
        lines.append(COURSES[k]["name"] + ":")
        for i, (title, files) in enumerate(COURSE_SECTIONS.get(k) or []):
            lines.append("  " + str(i + 1) + ". " + (title or "Урок " + str(i + 1)))
        lines.append("")
    lines.append("Йдемо по одному уроку: дивитесь відео, робите практику, тиснете «Далі». "
                 "Усе куплене завжди під рукою в меню «Мої матеріали».")
    send(uid, "\n".join(lines), kb)
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
                    + give_kb(uid, "t1", "Видати гайд вручну")["inline_keyboard"]}, uid=uid)
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
           + ("" if ok_c else "\nКурс у чат не пішов (" + ready_text("k12") + "), доступ і кабінет є."), uid=uid)


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


# ---------- розсилка push1 (13.10) ----------
#
# Слово Yaro 13.10 ~19:05 про тих, кому видали курси чи лід-магніти: «як ми їх будемо пушити?», «їх акуратно
# запушити, і потім ще і в цьому пуші додати кнопку переходу на телеграм-канал ще». Рамка 13.10 19:4x: «нативно»,
# подарунок першим, рядок про канал у кінці; кожному той безкоштовний подарунок, якого в нього ще нема.
#   G1: брали урок 1.5, а PDF «3 схеми світла» не отримали (подарунок після уроку міг не дійти через зависання
#       до d47a992): той самий PDF магніту, що дають GIFT_DONE і GIFT_LATE, текст G1 підписом під файлом,
#       кнопка каналу.
#   G2: брали схеми, а уроку 1.5 не мали (і курсу нема: урок у ньому): текст G2, кнопка уроку в кабінеті
#       (retush_lesson_url) поруч із кнопкою каналу.
#   Хто має і схеми, і урок (чи курс), поки нічого.
# Лише з рук персоналу (NOTIFY_IDS): /push1 це перегляд тому, хто питає (числа й обидва повідомлення так, як їх
# побачать люди); /push1 go шле раз на людину (kv push1:<id>), одна людина на секунду, лише 10:00–20:00 за
# Києвом, звіт тому, хто запустив. Тексти й підписи кнопок у push1.txt (змінні PUSH1_* перебивають файл), тож
# правка тексту не вимагає коду. Кнопка каналу веде на окреме запрошення push1 (рахує вступи), воно лише в
# змінній PUSH1_URL на Render.

PUSH_KEY = "push1"
PUSH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "push1.txt")
PUSH_SECTIONS = ("G1", "G2", "KNOPKA", "UROK", "URL")
PUSH_SEGS = ("G1", "G2")
PUSH_SEG_NAMES = {"G1": "брали урок 1.5, схем нема: дарую 3 схеми (PDF)",
                  "G2": "брали схеми, уроку 1.5 не мали: дарую урок"}
PUSH_STUB = "ЗАГЛУШКА"                      # слово в тексті = текст не затверджений, go не шле
PUSH_BTN = "Канал «для своїх»"
PUSH_UROK_BTN = "Відкрити урок"             # як у retush_magnet_kb
PUSH_CHANNEL = "https://t.me/iryna_rul_photographer"     # коли нема ні PUSH1_URL, ні CHANNEL_URL
PUSH_FROM_H, PUSH_TO_H = 10, 20             # лише денні години за Києвом
PUSH_PAUSE = 1.0                            # секунд між людьми
PUSH_MAX = 4096                             # ліміт тексту повідомлення Telegram
PUSH_CAPTION_MAX = 1024                     # ліміт підпису під файлом (G1)
PUSH_NAMES_MAX = 15                         # імен на сегмент у перегляді в Telegram
PUSH_GIFT_BUSY = timedelta(minutes=15)      # свіжа заявка gift:<id> = подарунок схем саме йде з іншого місця
# Кого не чіпаємо, крім персоналу (тест-акаунти, свої, друзі): id через кому лише в змінній Render,
# бо репозиторій публічний.
PUSH_SKIP_IDS = _ids(os.getenv("PUSH_SKIP_IDS", ""))
PUSH_COURSE = {"k1", "k2", "k12", "k12z"}
PUSH_GUIDE = {"t1", "t2", "t3"}
# «Стоп», відписка чи «не пишіть» у будь-якому повідомленні людини боту: розсилок їй не шлемо.
PUSH_STOP_RE = re.compile(r"(?<!\w)(?:стоп|stop|unsubscribe)(?!\w)|(?<!\w)(?:відпи[сш]|отпи[сш])|(?<!\w)не\s+пиш",
                          re.I)
PUSH_SKIP_WHY = ("персонал", "вручну (PUSH_SKIP_IDS)", "push1 уже був", "заблокували бота",
                 "писали «стоп»", "бот писав за 24 год")
_push_busy = threading.Lock()


def push1_texts(path=None):
    """Тексти розсилки: секції [G1], [G2], [KNOPKA], [UROK], [URL] з push1.txt; рядки до першої секції це
    коментар. Непорожня змінна Render PUSH1_<СЕКЦІЯ> перебиває файл («-» = порожньо, «\\n» = новий рядок)."""
    sec, cur = {}, None
    try:
        with open(path or PUSH_FILE, encoding="utf-8") as f:
            for line in f.read().splitlines():
                m = re.fullmatch(r"\[(\w+)\]", line.strip())
                if m and m.group(1).upper() in PUSH_SECTIONS:
                    cur = m.group(1).upper()
                    sec[cur] = []
                elif cur:
                    sec[cur].append(line.rstrip())
    except OSError as e:
        log.warning("push1.txt: %s", e)
    out = {k: "\n".join(sec.get(k) or []).strip() for k in PUSH_SECTIONS}
    for k in PUSH_SECTIONS:
        env = os.getenv("PUSH1_" + k, "").strip()
        if env:
            out[k] = "" if env == "-" else env.replace("\\n", "\n")
    return out


def push1_link(t):
    """Посилання кнопки каналу і звідки воно: інвайт push1 (PUSH1_URL), інакше CHANNEL_URL, інакше канал."""
    for url, src in ((t.get("URL"), "інвайт push1"), (CHANNEL_URL, "CHANNEL_URL, не інвайт push1"),
                     (PUSH_CHANNEL, "запасне, не інвайт push1")):
        if url and url.startswith("https://t.me/"):
            return url, src
    return PUSH_CHANNEL, "запасне, не інвайт push1"


def push1_kb(t, s):
    """Кнопки повідомлення сегмента: G1 лише канал; G2 урок у кабінеті поруч із каналом (один ряд)."""
    kanal = {"text": t.get("KNOPKA") or PUSH_BTN, "url": push1_link(t)[0]}
    if s == "G2":
        return {"inline_keyboard": [[{"text": t.get("UROK") or PUSH_UROK_BTN,
                                      "web_app": {"url": retush_lesson_url()}}, kanal]]}
    return {"inline_keyboard": [[kanal]]}


def push1_problems(t):
    """Чому go не шле з такими текстами; порожньо = можна."""
    out = []
    active = [s for s in PUSH_SEGS if t.get(s)]
    if not active:
        out.append("текстів нема")
    for s in active:
        if PUSH_STUB in t[s]:
            out.append("текст " + s + " ще " + PUSH_STUB)
        lim = PUSH_CAPTION_MAX if s == "G1" else PUSH_MAX
        if len(t[s]) > lim:
            out.append("текст " + s + " довший за " + str(lim) + " знаків")
    if "G1" in active and not magnet_ref():
        out.append("нема PDF схем (магніту) для G1")
    if "G2" in active and not retush_lesson_url():
        out.append("нема посилання на урок у кабінеті (KABINET_URL) для G2")
    if PUSH_STUB in (t.get("KNOPKA") or "") + (t.get("UROK") or ""):
        out.append("підпис кнопки ще " + PUSH_STUB)
    return out


def push1_window(now=None):
    return PUSH_FROM_H <= kyiv_hour(now) < PUSH_TO_H


def push1_segments(now=None):
    """Хто що отримає, з живої бази. G1: брали урок 1.5 (вхід за посиланням retush, урок у кабінеті чи подарунок
    уроку), а схем нема (кнопка, подарунок, push1). G2: мають схеми, уроку 1.5 не брали і курсу нема. Обидва
    (схеми й урок чи курс): поки нічого. Не шлемо: персоналу, PUSH_SKIP_IDS, кому push1 уже був, хто заблокував
    бота (403 пізніше за останній візит), хто писав «стоп», кому бот писав за 24 год (будь-яка подія людини чи її
    візит за добу: кожна відповідь бота йде з подією). None = бази нема або вона не відповіла."""
    rows = store.push_rows() if store.ON else None
    if rows is None:
        return None
    now = now or datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    staff = {i for i in [ADMIN_ID, IRA_ID] + NOTIFY_IDS + LEAD_IDS if i}
    skip_ids = set(PUSH_SKIP_IDS)
    seg = {s: [] for s in PUSH_SEGS}
    skip = {w: [] for w in PUSH_SKIP_WHY}
    both = none = 0
    for r in rows:
        uid = r.get("user_id")
        tiers = set(r.get("tiers") or [])
        magnet = bool(r.get("got_magnet_at") or r.get("ev_magnet"))
        lesson = bool(r.get("ev_lesson") or r.get("kab_lesson"))
        if lesson and not magnet:
            s = "G1"
        elif magnet and not lesson and not tiers & PUSH_COURSE:
            s = "G2"
        elif magnet:
            both += 1
            continue
        else:
            none += 1
            continue
        seen, blocked_at = r.get("last_seen_at"), r.get("blocked_at")
        last = [x for x in (r.get("last_event"), seen) if x]
        if uid in staff or (r.get("role") or "client") != "client":
            why = PUSH_SKIP_WHY[0]
        elif uid in skip_ids:
            why = PUSH_SKIP_WHY[1]
        elif r.get("push1"):
            why = PUSH_SKIP_WHY[2]
        elif blocked_at and not (seen and seen > blocked_at):
            why = PUSH_SKIP_WHY[3]
        elif PUSH_STOP_RE.search(r.get("texts") or ""):
            why = PUSH_SKIP_WHY[4]
        elif last and max(last) > day_ago:
            why = PUSH_SKIP_WHY[5]
        else:
            why = None
        buys = sorted(tiers & (PUSH_COURSE | PUSH_GUIDE))
        p = {"id": uid, "seg": s, "buys": buys,
             "who": who({"id": uid, "username": r.get("username"), "first_name": r.get("first_name"),
                         "last_name": r.get("last_name")}) + (" (купила: " + ", ".join(buys) + ")" if buys else "")}
        (skip[why] if why else seg[s]).append(p)
    return {"seg": seg, "skip": skip, "both": both, "none": none}


def push1_summary(sg, t, full=False, now=None):
    """Текст перегляду: числа, кнопки, стан текстів; full (сторінка /push1/<S>) поіменно всіх і тексти."""
    active = [s for s in PUSH_SEGS if t.get(s)]
    lines = ["push1, перегляд: нікому з людей нічого не надіслано.",
             "Зараз " + kyiv_now(now).strftime("%d.%m %H:%M") + " за Києвом; /push1 go шле лише 10:00–20:00"
             + (" (зараз можна)." if push1_window(now) else " (зараз ні).")]
    if sg is None:
        lines.append("База " + ("не відповіла" if store.ON else "вимкнена (нема DATABASE_URL)")
                     + ": людей не рахую, go не шле.")
    else:
        seg = sg["seg"]
        for s in PUSH_SEGS:
            nb = sum(1 for p in seg[s] if p["buys"])
            lines.append(s + ", " + PUSH_SEG_NAMES[s] + ": " + str(len(seg[s]))
                         + (" (з них з покупками " + str(nb) + ")" if nb else "")
                         + ("" if t.get(s) else " (тексту " + s + " нема: їм не шлемо)"))
        lines.append("Разом піде: " + str(sum(len(seg[s]) for s in active)))
        lines.append("Не шлемо: " + ", ".join(w + " " + str(len(v)) for w, v in sg["skip"].items()))
        lines.append("Мають і схеми, і урок 1.5 (чи курс): " + str(sg["both"]) + ", їм поки нічого.")
        lines.append("Ні схем, ні уроку 1.5 (лише /start чи лише покупки): " + str(sg["none"]) + ", не шлемо.")
    url, src = push1_link(t)
    lines.append("Кнопка «" + (t.get("KNOPKA") or PUSH_BTN) + "» у G1 і G2: " + url + " (" + src + ")")
    lines.append("Кнопка «" + (t.get("UROK") or PUSH_UROK_BTN) + "» у G2: "
                 + (retush_lesson_url() or "нема посилання (KABINET_URL)"))
    probs = push1_problems(t)
    lines.append("Тексти: " + ("готові, go шле їх дослівно." if not probs else "; ".join(probs) + ": go не шле."))
    if sg is not None:
        groups = [("Хто " + s, sg["seg"][s]) for s in PUSH_SEGS]
        groups += [("Не шлемо, " + w, v) for w, v in sg["skip"].items() if full or w == PUSH_SKIP_WHY[5]]
        for title, ppl in groups:
            if not ppl:
                continue
            cap = len(ppl) if full else PUSH_NAMES_MAX
            lines += ["", title + ":"] + ["  " + p["seg"] + "  " + p["who"] for p in ppl[:cap]]
            if len(ppl) > cap:
                lines.append("  і ще " + str(len(ppl) - cap))
    if full:
        for s in active:
            lines += ["", "Текст " + s + (" (підпис під PDF схем):" if s == "G1" else ":"), t[s]]
        return "\n".join(lines)
    if active:
        lines += ["", "Нижче повідомлення так, як їх побачать люди: "
                  + ", потім ".join(s + (" (PDF схем з підписом)" if s == "G1" else " (кнопки уроку й каналу)")
                                    for s in active) + "."]
    text = "\n".join(lines)
    return text if len(text) <= STATS_TEXT_MAX else text[:STATS_TEXT_MAX - 1] + "…"


def push1_preview(to):
    """/push1: підсумок і кожне повідомлення рівно так, як його побачать люди. Лише тому, хто питав."""
    t = push1_texts()
    send(to, push1_summary(push1_segments(), t))
    for s in PUSH_SEGS:
        if t.get(s):
            j = _push1_deliver(to, s, t)
            if not j.get("ok"):
                send(to, "Перегляд " + s + " не пішов: " + str(j.get("description"))[:200])


def push1_spawn(fn):
    threading.Thread(target=fn, daemon=True, name="push1").start()


def push1_go(by, now=None):
    """/push1 go: перевірки, потім фоновий потік розсилки. Повертає відповідь тому, хто запустив."""
    if not store.ON:
        return "Бази нема: без неї не знаю, кому вже надіслано. push1 нікому не надіслано."
    if not push1_window(now):
        return ("Зараз " + kyiv_now(now).strftime("%H:%M") + " за Києвом. push1 шле лише 10:00–20:00, "
                "нікому не надіслано.")
    t = push1_texts()
    probs = push1_problems(t)
    if probs:
        return "push1 нікому не надіслано: " + "; ".join(probs) + "."
    if not _push_busy.acquire(blocking=False):
        return "push1 уже йде, звіт прийде сюди."
    try:
        sg = push1_segments(now)
        if sg is None:
            _push_busy.release()
            return "База не відповіла, push1 нікому не надіслано. Спробуй ще раз за хвилину."
        targets = [(p["id"], s) for s in PUSH_SEGS if t.get(s) for p in sg["seg"][s]]
        if not targets:
            _push_busy.release()
            return "push1: нікому слати (усі вже отримали або не підходять). /push1 покаже, хто де."
        n = {s: len(sg["seg"][s]) for s in PUSH_SEGS if t.get(s)}
        push1_spawn(lambda: _push1_worker(by, targets, t))
    except BaseException:
        if _push_busy.locked():
            _push_busy.release()
        raise
    return ("Почала push1: " + ", ".join(s + " " + str(v) for s, v in n.items()) + ", разом " + str(len(targets))
            + ", одна людина на секунду (~" + str(len(targets)) + " с). Звіт пришлю сюди.")


def _push1_deliver(uid, s, t):
    """Одне повідомлення сегмента s (людині, а в перегляді персоналу так само): G1 PDF схем з підписом G1 і
    кнопкою каналу; G2 текст G2 з кнопками уроку й каналу. На 429 чекаємо, скільки просить Telegram (до 60 с),
    до трьох разів. Повертає сиру відповідь Telegram."""
    kb = push1_kb(t, s)
    j = {}
    for _ in range(4):
        if s == "G1":
            j = api_raw("sendDocument", chat_id=uid, document=magnet_ref(), caption=t[s][:PUSH_CAPTION_MAX],
                        reply_markup=kb)
        else:
            j = api_raw("sendMessage", chat_id=uid, text=t[s][:PUSH_MAX], reply_markup=kb,
                        disable_web_page_preview=True)
        if j.get("error_code") != 429:
            return j
        wait = (j.get("parameters") or {}).get("retry_after") or 3
        if wait > 60:
            return j
        time.sleep(wait + 0.3)
    return j


def _push1_g1_busy(uid, now=None):
    """Чому G1 зараз не дарувати схеми; порожньо = можна. Схеми вже є (подарунок після уроку дійшов) чи подарунок
    саме йде з іншого місця (свіжа заявка gift:<id>). Стара заявка без схем = подарунок тоді не дійшов: даруємо.
    Заявку gift:<id> ставимо самі, тож подарунок після уроку вже не продублює."""
    u = store.get_user(uid) or {}
    if u.get("got_magnet_at"):
        return "уже мали схеми"
    if store.kv_claim("gift:" + str(uid)):
        return ""
    row = store.q("select updated_at from kv where k = %s", ("gift:" + str(uid),), fetch="one") or {}
    at = row.get("updated_at")
    if at and at > (now or datetime.now(timezone.utc)) - PUSH_GIFT_BUSY:
        return "подарунок схем саме йде"
    return ""


def _push1_worker(by, targets, t):
    """Розсилка по черзі: заявка kv push1:<id> до відправки (вдруге та сама людина не отримає ніколи), подія
    push1 на кожного, G1 ставить схеми (got_magnet_at, подія magnet via push1), G2 подію lesson_gift; 403 =
    позначка blocked:<id> (ставить api_raw). Вікно закрилось чи сервер зупиняють: решту не чіпаємо, наступний
    /push1 go їх дошле. Наприкінці звіт тому, хто запустив."""
    sent = {s: 0 for s in PUSH_SEGS if t.get(s)}
    blocked, errors, had = [], [], []
    already = nodb = left = 0
    try:
        for i, (uid, s) in enumerate(targets):
            if STOP.is_set() or not push1_window():
                left = len(targets) - i
                break
            key = PUSH_KEY + ":" + str(uid)
            store.session_begin()
            try:
                if s == "G1":
                    why = _push1_g1_busy(uid)
                    if why:
                        had.append(str(uid) + " " + why)
                        continue
                if not store.kv_claim(key):
                    if store.kv_get(key):
                        already += 1
                    else:
                        nodb += 1
                    continue
                if s == "G2":
                    kabinet_mist.push_user(uid)            # людина в базі кабінету до кнопки уроку
                j = _push1_deliver(uid, s, t)
                if j.get("ok"):
                    sent[s] += 1
                    store.kv_set(key, "ok " + s)
                    if s == "G1":
                        store.mark_magnet(uid)
                        store.log_event(uid, "magnet", {"via": PUSH_KEY})
                        kabinet_mist.push_user(uid)
                    else:
                        store.log_event(uid, "lesson_gift", {"via": PUSH_KEY})
                    store.log_event(uid, PUSH_KEY, {"seg": s, "ok": True})
                elif j.get("error_code") == 403:
                    blocked.append(uid)
                    store.kv_set(key, "403 " + s)
                    store.log_event(uid, PUSH_KEY, {"seg": s, "ok": False, "err": str(j.get("description"))[:200]})
                else:
                    errors.append(str(uid) + ": " + str(j.get("description"))[:100])
                    store.kv_set(key, "err " + s)
                    store.log_event(uid, PUSH_KEY, {"seg": s, "ok": False, "err": str(j.get("description"))[:200]})
            finally:
                store.session_end()
            if i + 1 < len(targets):
                time.sleep(PUSH_PAUSE)
        lines = ["push1 готово: надіслано " + str(sum(sent.values())) + " ("
                 + ", ".join(s + " " + str(v) for s, v in sent.items()) + ")."]
        if blocked:
            lines.append("Заблокували бота: " + str(len(blocked)) + " (id " + ", ".join(map(str, blocked))
                         + "), позначені, розсилки їх більше не чіпають.")
        if errors:
            lines.append("Не пішло з іншої причини: " + str(len(errors)) + " (" + "; ".join(errors) + ").")
        if had:
            lines.append("G1 не надіслано, бо схеми вже є чи саме йдуть: " + str(len(had)) + " (" + "; ".join(had) + ").")
        if already:
            lines.append("Уже отримали раніше: " + str(already) + ".")
        if nodb:
            lines.append("База не відповіла: " + str(nodb) + ", не надіслано; наступний /push1 go дошле.")
        if left:
            lines.append("Не встигла до 20:00 за Києвом" + (" (зупинка сервера)" if STOP.is_set() else "")
                         + ": " + str(left) + "; наступний /push1 go дошле, повторів не буде.")
        store.session_begin()
        try:
            store.log_event(by, "push1_run", {"sent": sent, "blocked": len(blocked), "err": len(errors),
                                              "had": len(had), "already": already, "nodb": nodb, "left": left})
        finally:
            store.session_end()
        send(by, "\n".join(lines))
    except Exception as e:
        log.exception("push1")
        send(by, "push1 зламався посередині: " + str(e)[:200] + ". Надіслане не повториться; /push1 покаже решту.")
    finally:
        _push_busy.release()


# ---------- люди (13.10): одна жива таблиця з бази, лише читання ----------
#
# Скарга Yaro 13.10 19:4x: обліку ніхто не веде, усе плутається, незрозуміло, хто в каналі і на якому етапі.
# /lyudy/<S> (той самий секрет, що /db): угорі зведення (скільки людей на кожному етапі і скільки з них у каналі),
# далі картка на людину: хто, звідки прийшла і коли, що отримала, коли і як (оплата, вручну /vydaty, МК), заявка
# МК, чи в каналі (getChatMember: бот адмін каналу), останній дотик, етап одним словом. ?md=1 дає те саме
# Markdown-текстом. Позначки людей поза персоналом (акаунти Yaro, друг, тест) лише в змінній LYUDY_MARKS на
# Render («id:позначка,id:позначка»), бо репо публічний. Позначені й персонал у етапах не рахуються.

def _marks(raw):
    out = {}
    for part in (raw or "").split(","):
        i, _, mark = part.strip().partition(":")
        try:
            out[int(i)] = mark.strip() or "позначка"
        except ValueError:
            pass
    return out


LYUDY_MARKS = _marks(os.getenv("LYUDY_MARKS", ""))
LYUDY_STAGES = ("МК", "курс", "гайд", "урок", "схеми", "старт")
LYUDY_STAGE_NAMES = {"МК": "гайд і курс за посиланням МК", "курс": "курс (оплата чи вручну)",
                     "гайд": "гайд без курсу", "урок": "безкоштовний урок 1.5, без покупок",
                     "схеми": "лише 3 схеми світла, без покупок", "старт": "лише /start, нічого не отримали"}
LYUDY_COURSE = ("k1", "k2", "k12", "k12z")
LYUDY_CORE = ("прийшла", "3 схеми", "урок 1.5", "гайд", "курс", "останній дотик")   # решта рядків картки лише коли є що сказати
LYUDY_MANUAL_WINDOW = timedelta(minutes=10)    # ручна видача і рядок покупки в межах цих хвилин = одна дія
LYUDY_KINDS = {"start": "/start", "magnet": "3 схеми", "retush_entry": "вхід в урок 1.5", "message": "повідомлення",
               "give_manual": "ручна видача", "pay_ok": "оплата", "push1": "push1", "staff_reply": "відповідь персоналу",
               "mk_grant": "видача МК", "mk_want": "заявка МК", "mk_open": "опис МК (цікавиться)", "mk_entry": "кнопка МК в каналі",
               "kanal_btn": "кнопка каналу", "lesson": "урок курсу", "practice": "практика",
               "guide_open": "картка гайда", "retush_open": "картка курсу", "tier_pick": "вибір тарифу",
               "keyword": "слово", "kurs_entry": "вхід курсу", "guide_entry": "вхід гайда", "mk_again": "МК вдруге",
               "lesson_gift": "подарунок уроку 1.5", "sub_check": "натиск «Я підписалась»",
               "sub_ok": "підписка підтверджена", "gate": "ворота ціни (Т9)", "zapr_open": "«Розкажіть про курс»",
               "touch": "дотик воронки", "svitlo_entry": "вхід svitlo/profil", "preset_entry": "вхід пресет"}
KANAL_TTL = 600                                # секунд памʼятаємо відповідь getChatMember
KANAL_MAX = 200                                # нових запитів getChatMember за одне відкриття сторінки
_kanal_cache = {}                              # uid -> (коли, (True/False/None, пояснення))
KANAL_STATUS = {"creator": (True, "так (власник)"), "administrator": (True, "так (адмін)"),
                "member": (True, "так"), "left": (False, "ні"), "kicked": (False, "ні (заблокована в каналі)")}
LYUDY_CSS = ("body{font:15px/1.45 -apple-system,system-ui,Roboto,'Segoe UI',sans-serif;margin:0;padding:12px;"
             "background:#fff;color:#111}h1{font-size:20px;margin:0 0 2px}h2{font-size:17px;margin:22px 0 6px}"
             ".s{color:#666;font-size:13px}.p{border:1px solid #ddd;border-radius:10px;padding:8px 10px;margin:8px 0;"
             "overflow-wrap:anywhere}.h{font-weight:600}.m{color:#a40000;font-weight:600}"
             "table{border-collapse:collapse;margin:6px 0}td,th{padding:3px 12px 3px 0;text-align:left}"
             "td.n{text-align:right}ul{margin:6px 0;padding-left:18px}")


def _kt(dt):
    """Час за Києвом коротко; нема = «—»."""
    return kyiv_now(dt).strftime("%d.%m %H:%M") if dt else "—"


def kanal_member(uid):
    """Чи людина в каналі: getChatMember (бот адмін каналу). (True/False/None, пояснення); кеш KANAL_TTL."""
    hit = _kanal_cache.get(uid)
    if hit and time.time() - hit[0] < KANAL_TTL:
        return hit[1]
    if not CHANNEL_ID:
        return (None, "невідомо: канал не заданий (CHANNEL_ID чи CHANNEL_URL)")
    j = api_raw("getChatMember", chat_id=CHANNEL_ID, user_id=uid)
    if j.get("ok"):
        r = j.get("result") or {}
        st = r.get("status")
        if st == "restricted":
            res = (True, "так (з обмеженнями)") if r.get("is_member") else (False, "ні")
        else:
            res = KANAL_STATUS.get(st, (None, "невідомо: статус " + str(st)))
    else:
        d = str(j.get("description") or "немає відповіді")
        res = (None, "невідомо: " + ("бот не адмін каналу (" + d[:80] + ")"
                                     if "inaccessible" in d or "not enough rights" in d else "Telegram: " + d[:120]))
    _kanal_cache[uid] = (time.time(), res)
    return res


def kanal_many(uids):
    """getChatMember для багатьох у 4 потоки, не більше KANAL_MAX нових за раз (решта з кешу чи «оновіть»)."""
    fresh = time.time() - KANAL_TTL
    need = [u for u in uids if not (_kanal_cache.get(u) and _kanal_cache[u][0] > fresh)][:KANAL_MAX]
    if need:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(kanal_member, need))
    return {u: (_kanal_cache.get(u) or (0, (None, "невідомо: ще не перевірено, оновіть сторінку")))[1]
            for u in uids}


def _lyudy_how(p, e):
    """Як видано покупку: МК, оплата (подія pay_ok з тим самим кодом), вручну (/vydaty чи кнопка, ±10 хв), тест."""
    oc = p.get("order_code") or ""
    if oc.startswith("MK") or p.get("source_tag") == "mk":
        return "МК"
    pairs = lambda kind: list(zip((e.get(kind) or {}).get("all_at") or [], (e.get(kind) or {}).get("all_p") or []))
    if any((pl or {}).get("code") == oc for _, pl in pairs("pay_ok")):
        return "оплата"
    when = p.get("paid_at") or p.get("delivered_at")
    for kind, word in (("give_manual", "вручну"), ("pay_test", "тест оплати")):
        for at, pl in pairs(kind):
            if (pl or {}).get("ok") and when and at and abs(at - when) <= LYUDY_MANUAL_WINDOW:
                return word
    return "спосіб невідомий"


def _lyudy_buys(ps, e, tiers):
    """Рядок покупок одного виду: оплачені й видані з часом і способом; обрані без оплати окремо."""
    done = [p for p in ps if p.get("tier") in tiers and p.get("status") in ("paid", "delivered")]
    new = [p for p in ps if p.get("tier") in tiers and p.get("status") not in ("paid", "delivered")]
    parts = []
    for p in done:
        how = _lyudy_how(p, e)
        amt = p.get("amount_uah")
        parts.append(pname(p["tier"]) + " (" + p["tier"] + "), " + _kt(p.get("delivered_at") or p.get("paid_at"))
                     + ", " + how + (", " + str(amt) + " грн" if how == "оплата" and amt else "")
                     + ("" if p.get("status") == "delivered" else ", оплачено, не видано"))
    for p in new:
        parts.append("обрала " + p["tier"] + " " + _kt(p.get("created_at")) + ", не оплачено")
    return done, "; ".join(parts) or "—"


def lyudy_rows(data, now=None):
    """Картки людей зі store.people_data(): словник на людину з етапом, позначками й полями картки."""
    now = now or datetime.now(timezone.utc)
    users = {u["user_id"]: u for u in data.get("users") or []}
    pur, ev, kv, kp = {}, {}, {}, {}
    for p in data.get("purchases") or []:
        pur.setdefault(p["user_id"], []).append(p)
    for x in data.get("events") or []:
        ev.setdefault(x["user_id"], {})[x["kind"]] = x
    for r in data.get("kv") or []:
        parts = (r.get("k") or "").split(":")
        try:
            uid = int(parts[1])
        except (IndexError, ValueError):
            continue
        if parts[0] == "kp" and len(parts) == 4:
            kp.setdefault(uid, {}).setdefault(parts[2], {})[parts[3]] = r.get("updated_at")
        elif len(parts) == 2:
            kv.setdefault(uid, {})[parts[0]] = (r.get("v"), r.get("updated_at"))
    staff = set(staff_ids()) | set(LEAD_IDS) | ({ADMIN_ID} if ADMIN_ID else set())
    rows = []
    for uid in sorted(set(users) | set(pur) | set(ev)):
        u, e, ps, k = users.get(uid) or {}, ev.get(uid) or {}, pur.get(uid) or [], kv.get(uid) or {}
        marks = []
        if uid in staff or (u.get("role") or "client") != "client":
            marks.append("персонал")
        if uid in LYUDY_MARKS:
            marks.append(LYUDY_MARKS[uid])
        name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x) or "без імені"
        who_s = name + ", " + ("@" + u["username"] if u.get("username") else "без юзернейма") + ", id " + str(uid)
        firsts = [x["first_at"] for x in e.values() if x.get("first_at")]
        tag = u.get("source_tag") or ((e.get("start") or {}).get("first_p") or {}).get("tag") or "без мітки"
        came = u.get("created_at") or (min(firsts) if firsts else None)
        mg_ev = e.get("magnet") or {}
        mg_at = u.get("got_magnet_at") or mg_ev.get("first_at")
        mg_p = mg_ev.get("first_p") or {}
        mg_via = ("" if not mg_at else "подарунок після уроку" if mg_p.get("via") == "gift"
                  else "push1" if mg_p.get("via") == "push1" else "стара кнопка" if mg_p.get("legacy")
                  else "кнопка «Забрати три схеми»" if mg_ev else "позначка в базі")
        l15 = (kp.get(uid) or {}).get("1.5") or {}
        l_entry = (e.get("retush_entry") or {}).get("first_at")
        l_gift = (e.get("lesson_gift") or {}).get("first_at")     # урок подаровано (push1 G2)
        lesson = bool(l_entry or l_gift or l15)
        guide_done, guide_s = _lyudy_buys(ps, e, TIERS)
        course_done, course_s = _lyudy_buys(ps, e, LYUDY_COURSE)
        mk = bool(e.get("mk_grant")) or any((p.get("order_code") or "").startswith("MK")
                                            and p.get("status") in ("paid", "delivered") for p in ps)
        stage = ("МК" if mk else "курс" if course_done else "гайд" if guide_done
                 else "урок" if lesson else "схеми" if mg_at else "старт")
        parts = {n: v for n, v in (kp.get(uid) or {}).items() if n != "1.5"}
        want = e.get("mk_want") or {}
        mk_open, mk_entry = e.get("mk_open"), e.get("mk_entry")
        touches = [(u.get("last_seen_at"), "писала чи тиснула в боті")] + [
            (x.get("last_at"), LYUDY_KINDS.get(kd, kd)) for kd, x in e.items()]
        touches = [t for t in touches if t[0]]
        last = max(touches, key=lambda t: t[0]) if touches else (None, "")
        bl = k.get("blocked")
        seen = u.get("last_seen_at")
        msg = e.get("message") or {}
        rows.append({
            "id": uid, "tag": tag, "who": who_s, "marks": marks, "stage": stage, "kanal": (None, "невідомо: ще не перевірено"),
            "schemes": bool(mg_at), "lesson": lesson, "guide": bool(guide_done), "course": bool(course_done),
            "mk": mk, "want": bool(want), "last_at": last[0],
            "blocked": bool(bl and bl[1] and (not seen or bl[1] > seen)),
            "push1": (k.get("push1") or (None,))[0],
            "f": [x for x in [
                ("прийшла", tag + ", " + _kt(came)),
                ("3 схеми", (_kt(mg_at) + ", " + mg_via) if mg_at else "—"),
                ("урок 1.5", (("вхід " + _kt(l_entry) if l_entry or not l_gift else "подарунок " + _kt(l_gift))
                              + " · відкрила " + _kt(l15.get("start"))
                              + " · додивилась " + _kt(l15.get("done"))) if lesson else "—"),
                ("гайд", guide_s),
                ("курс", course_s),
                ("кабінет, інші частини", ("почала " + str(sum(1 for v in parts.values() if v.get("start")))
                                           + ", додивилась " + str(sum(1 for v in parts.values() if v.get("done")))
                                           ) if parts else "—"),
                ("МК", ("гість за посиланням МК, " + _kt((e.get("mk_grant") or {}).get("first_at"))) if mk else
                 ("заявка " + _kt(want.get("first_at")) + (" (натискань: " + str(want["n"]) + ")"
                                                          if want.get("n", 0) > 1 else "")) if want else
                 ("дивилась опис " + _kt(mk_open["first_at"]) + ", заявки нема") if mk_open else
                 ("кнопка в каналі " + _kt(mk_entry["first_at"]) + ", детальніше не тиснула") if mk_entry else "—"),
                ("писала боту", (str(msg["n"]) + ", останнє " + _kt(msg.get("last_at"))) if msg else "—"),
                ("останній дотик", (_kt(last[0]) + " (" + last[1] + ")") if last[0] else "—"),
            ] + ([("заблокувала бота", _kt(bl[1]))] if bl and bl[1] and (not seen or bl[1] > seen) else [])
              + ([("push1", str(k["push1"][0]))] if k.get("push1") else []) if x[1] != "—" or x[0] in LYUDY_CORE],
        })
    return rows


def _svitlo_line(cnt):
    """По мітках svitlo, profil, storis, svit і hajd299: скільки людей, скільки отримали файл, скільки в каналі (за перевіркою), скільки взяли гайд."""
    out = []
    for t in SVITLO_TAGS + (HAJD_TAG,):
        g = [r for r in cnt if (r.get("tag") or "").lower() == t]
        out.append(t + " " + str(len(g)) + " / " + str(sum(1 for r in g if r["schemes"])) + " / "
                   + str(sum(1 for r in g if r["kanal"][0] is True)) + " / " + str(sum(1 for r in g if r["guide"])))
    return "; ".join(out)


def lyudy_summary(rows):
    """Зведення угорі: етапи (і скільки з них у каналі), безкоштовне без покупок, МК, блоки, push1."""
    cnt = [r for r in rows if not r["marks"]]
    by = {s: [r for r in cnt if r["stage"] == s] for s in LYUDY_STAGES}
    free = by["урок"] + by["схеми"]
    unk = [r for r in cnt if r["kanal"][0] is None]
    why = sorted(set(r["kanal"][1].replace("невідомо: ", "", 1) for r in unk))
    return {
        "table": [(s, len(by[s]), sum(1 for r in by[s] if r["kanal"][0] is True)) for s in LYUDY_STAGES],
        "lines": [
            "Людей у базі: " + str(len(rows)) + "; у підрахунку " + str(len(cnt)) + " (персонал і позначені окремо: "
            + str(len(rows) - len(cnt)) + ").",
            "У каналі: " + str(sum(1 for r in cnt if r["kanal"][0] is True)) + " з " + str(len(cnt))
            + ("; невідомо " + str(len(unk)) + " (" + "; ".join(why)[:300] + ")" if unk else "") + ".",
            "Безкоштовне без покупок: лише схеми " + str(sum(1 for r in free if r["schemes"] and not r["lesson"]))
            + ", лише урок 1.5 " + str(sum(1 for r in free if r["lesson"] and not r["schemes"]))
            + ", обидва " + str(sum(1 for r in free if r["lesson"] and r["schemes"])) + ".",
            "Входи світла (людей / файл / у каналі / гайд): " + _svitlo_line(cnt) + ".",
            "Заявок на МК (людей): " + str(sum(1 for r in cnt if r["want"])) + "; гостей МК: " + str(len(by["МК"])) + ".",
            "Заблокували бота: " + str(sum(1 for r in cnt if r["blocked"])) + "; push1 отримали: "
            + str(sum(1 for r in cnt if (r["push1"] or "").startswith("ok"))) + ".",
        ],
    }


def _lyudy_groups(rows):
    """Розділи сторінки: етапи по черзі (свіжий дотик згори), позначені й персонал наприкінці."""
    key = lambda r: r["last_at"] or datetime.min.replace(tzinfo=timezone.utc)
    out = [(s + ": " + LYUDY_STAGE_NAMES[s], sorted([r for r in rows if not r["marks"] and r["stage"] == s],
                                                   key=key, reverse=True)) for s in LYUDY_STAGES]
    out.append(("Персонал і позначені (в етапах не рахуються)", sorted([r for r in rows if r["marks"]],
                                                                       key=key, reverse=True)))
    return [(t, g) for t, g in out if g]


def lyudy_md(rows, now=None):
    sm = lyudy_summary(rows)
    out = ["# Люди бота @iryna_rul_bot", "", "Знято " + kyiv_now(now).strftime("%d.%m.%Y %H:%M")
           + " за Києвом зі сторінки /lyudy (лише читання). Час у картках київський.", "", "## Зведення", "",
           "| етап | людей | у каналі |", "|---|---|---|"]
    out += ["| " + s + " | " + str(n) + " | " + str(k) + " |" for s, n, k in sm["table"]]
    out += [""] + ["- " + x for x in sm["lines"]]
    for title, grp in _lyudy_groups(rows):
        out += ["", "## " + title + " (" + str(len(grp)) + ")"]
        for r in grp:
            out += ["", "### " + r["who"],
                    "- етап: " + r["stage"] + (" · позначка: " + ", ".join(r["marks"]) if r["marks"] else "")
                    + " · канал: " + r["kanal"][1]]
            out += ["- " + n + ": " + v for n, v in r["f"]]
    return "\n".join(out) + "\n"


def lyudy_html(rows, now=None):
    esc = lambda s: html.escape(str(s), quote=True)
    sm = lyudy_summary(rows)
    out = ['<!doctype html><html lang="uk"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Люди бота</title>',
           "<style>" + LYUDY_CSS + "</style></head><body>", "<h1>Люди бота</h1>",
           '<div class="s">' + esc(kyiv_now(now).strftime("%d.%m.%Y %H:%M"))
           + " за Києвом, лише читання; ?md=1 дає текст</div>",
           "<table><tr><th>етап</th><th>людей</th><th>у каналі</th></tr>"]
    out += ['<tr><td>' + esc(s) + '</td><td class="n">' + str(n) + '</td><td class="n">' + str(k) + "</td></tr>"
            for s, n, k in sm["table"]]
    out += ["</table><ul>"] + ["<li>" + esc(x) + "</li>" for x in sm["lines"]] + ["</ul>"]
    for title, grp in _lyudy_groups(rows):
        out.append("<h2>" + esc(title) + " (" + str(len(grp)) + ")</h2>")
        for r in grp:
            out.append('<div class="p"><div class="h">' + esc(r["who"]) + "</div><div>етап: <b>" + esc(r["stage"])
                       + "</b>" + (' · <span class="m">' + esc(", ".join(r["marks"])) + "</span>" if r["marks"] else "")
                       + " · канал: " + esc(r["kanal"][1]) + "</div>"
                       + "".join("<div>" + esc(n) + ": " + esc(v) + "</div>" for n, v in r["f"]) + "</div>")
    out.append("</body></html>")
    return "\n".join(out)


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
    how = ""
    if m:
        try:
            uid = unb36(m.group(1).upper())
        except Exception:
            return
        key = BY_CODE.get(m.group(2), "t" + m.group(2))
        code = "IR" + m.group(1).upper() + "-" + m.group(2)
    else:
        # 19.10: оплата за посиланням на картку Іри, коду у виписці нема. Одна людина
        # з незакритим тарифом на цю суму за добу = її оплата. Решта вхідних на картку
        # не наші: мовчимо, крім сум, що збігаються з ціною товару.
        rows = []
        if amount > 0 and amount % 100 == 0:
            try:
                rows = store.pending_by_amount(amount // 100)
            except Exception as e:
                log.warning("pending_by_amount: %s", e)
        uids = list(dict.fromkeys(r["user_id"] for r in rows))
        uids_all = uids
        when = tx.get("time")
        # 20.10: Тетяна обрала тариф о 9:31, заплатила о 9:33, а бот питав адміна, бо той самий
        # тариф за добу брали ще троє (учора). Коли кандидатів кілька, лишаємо тих, хто обрав
        # тариф за останні PICK_WIN секунд до платежу; один такий = його оплата.
        if len(uids) > 1 and when:
            fresh = [r for r in rows if r.get("pick_ts") and 0 <= when - float(r["pick_ts"]) <= PICK_WIN]
            fresh_uids = list(dict.fromkeys(r["user_id"] for r in fresh))
            if len(fresh_uids) == 1:
                rows, uids = fresh, fresh_uids
        when = time.strftime("%d.%m %H:%M", time.localtime(when)) if when else "час невідомий"
        if len(uids) > 1:
            names = []
            for r in rows:
                tu = store.get_user(r["user_id"]) or {}
                names.append(who({"id": r["user_id"], "username": tu.get("username"), "first_name":
                                  tu.get("first_name"), "last_name": tu.get("last_name")}) + ", " + r["order_code"])
            # нічия оплата: хто з кандидатів натисне «оплатила» протягом NECHYIA_WIN, тому бот видасть сам (claim_nechyia)
            store.kv_set("tx_nechyia", json.dumps({"id": tx.get("id"), "uah": amount // 100,
                                                   "time": tx.get("time") or int(time.time()), "uids": uids}))
            notify("Оплата " + str(amount // 100) + " грн на картці (" + when + "), а тариф на цю суму за добу брали кілька людей:\n"
                   + "\n".join(names) + "\n\nВпізнай і видай /vydaty. Якщо хтось із них натисне «оплатила», бот видасть сам.")
            return
        if not uids:
            if amount // 100 in {p.get("uah") for p in PRODUCTS.values()}:
                notify("Оплата " + str(amount // 100) + " грн на картці, але чия, не видно: коду нема, тариф на цю суму за добу ніхто не брав.\n"
                       "Коли: " + when + "\n"
                       "Від кого: " + (tx.get("description") or "не вказано") + "\n"
                       "Коментар: " + (tx.get("comment") or "порожній") + "\n\n"
                       "БЕЗ КОДУ: впізнай по імені і видай вручну.")
            return
        r = rows[0]
        uid, key, code = r["user_id"], r["tier"], r["order_code"]
        how = " (впізнано за сумою і часом)" if len(uids_all) > 1 else " (впізнано за сумою)"
    _pay_issue(uid, key, code, amount, how)


NECHYIA_WIN = int(os.getenv("NECHYIA_WIN", "2700"))   # с: «оплатила» не пізніше ніж за 45 хв після нічиєї оплати


def claim_nechyia(uid, key):
    """
    20.10: оплата без коду на суму, яку за добу брали кілька людей, лежить у kv як «нічия».
    Людина з того списку тисне «оплатила» протягом NECHYIA_WIN після платежу, і тариф
    сходиться за сумою: видаємо їй і забираємо запис. True = видано.
    """
    try:
        raw = store.kv_get("tx_nechyia")
        if not raw:
            return False
        d = json.loads(raw)
        if uid not in d.get("uids", []) or time.time() - float(d.get("time") or 0) > NECHYIA_WIN:
            return False
        if (osobysta_tsina(uid, key) or PRODUCTS.get(key, {}).get("uah", 0)) != d.get("uah"):
            return False
        if not store.kv_claim("tx_nechyia_" + str(d.get("id"))):
            return False
        store.kv_set("tx_nechyia", "")
    except Exception as e:
        log.warning("claim_nechyia: %s", e)
        return False
    _pay_issue(uid, key, order_code(uid, key), d["uah"] * 100, " (впізнано за сумою і кнопкою «оплатила»)")
    return True


def _pay_issue(uid, key, code, amount, how=""):
    """Оплата впізнана: записати, видати, сказати адміну. amount у копійках."""
    need = (osobysta_tsina(uid, key) or PRODUCTS.get(key, {}).get("uah", 0)) * 100
    if amount < need * 0.9:
        store.log_event(uid, "pay_short", {"code": code, "uah": amount // 100})
        notify("Оплата " + str(amount // 100) + " грн за кодом " + code
               + ", а треба " + str(need // 100) + " грн. " + pname(key) + ": не видано.", uid=uid)
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
        notify("Оплата " + str(amount // 100) + " грн, код " + code + how + ". "
               + pname(key) + ": видано автоматично.", uid=uid)
    else:
        notify("Оплата " + str(amount // 100) + " грн, код " + code
               + ", але файл не пішов. " + pname(key) + ": " + ready_text(key),
               give_kb(uid, key), uid=uid)


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
            # 21.10: MONO_JAR може бути списком через кому (перехід між картками):
            # Mono пускає 1 запит виписки на 60 с, тому рахунки читаємо по черзі, один за цикл.
            jars = [j.strip() for j in MONO_JAR.split(",") if j.strip()]
            jar = jars[int(time.time() // 70) % len(jars)]
            r = requests.get(MONO + "/personal/statement/" + jar + "/" + str(frm),
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
        "Оплата за посиланням: " + ("підключена" if PAY_URL else "не підключена")
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
 ul{padding-left:20px} li{margin:4px 0} hr{border:0;border-top:1px solid #dadde1;margin:36px 0}
 code{background:#f0f2f5;padding:1px 5px;border-radius:4px} a{color:#0064d1}
</style></head><body>

<h1>Політика конфіденційності</h1>
<div class="d">Telegram-бот <code>@iryna_rul_bot</code>, кабінет курсу і застосунок Meta
<code>iryna-reklama</code> &middot; оновлено 13 жовтня 2026 &middot; <a href="#en">English</a></div>

<h2>Чий це бот</h2>
<p>Бот належить Ірині, бʼюті і фешн фотографу з Києва і Житомира (Instagram
<a href="https://www.instagram.com/iryna_rul_photographer/">@iryna_rul_photographer</a>).
Через нього вона видає свої матеріали з фотографії і ретуші: безкоштовні уроки, гайд і курс,
і відповідає на питання. Бот, його сервер і застосунок Meta технічно обслуговує Ярослав Копчик.</p>

<h2>Контакти</h2>
<ul>
 <li>Ірина: Direct в Instagram
     <a href="https://www.instagram.com/iryna_rul_photographer/">@iryna_rul_photographer</a>
     або повідомлення в бот <a href="https://t.me/iryna_rul_bot">@iryna_rul_bot</a>.</li>
 <li>Дані і технічні питання: <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>
     (Ярослав Копчик).</li>
</ul>

<h2>Які дані бере бот</h2>
<ul>
 <li>Профіль Telegram: числовий ID, імʼя, прізвище і @username так, як вони вказані у вашому Telegram.
     Номера телефону бот не бачить і не просить.</li>
 <li>Звідки ви прийшли: мітку посилання, яким ви відкрили бот (наприклад, з реклами чи з каналу).</li>
 <li>Час першого візиту і останньої дії.</li>
 <li>Що ви робите в боті і кабінеті курсу: натиснуті кнопки, отримані й відкриті матеріали, переглянуті уроки.</li>
 <li>Ваші повідомлення боту (зберігаємо перші 300 знаків) і файли, які ви надсилаєте.
     Їх бачать Ірина й адміністратор, щоб вам відповісти.</li>
 <li>Покупки: що куплено, код замовлення, сума в гривнях, час оплати й видачі. Оплата проходить
     через Monobank; бот бачить лише суму, час, коментар до платежу і підпис платника у виписці.
     Даних картки бот не отримує.</li>
 <li>Чи ви в Telegram-каналі Ірини і чи не заблокували бот.</li>
</ul>

<h2>Навіщо</h2>
<ul>
 <li>Видати матеріали і доступ до курсу, які ви отримали чи купили, і зберегти цей доступ.</li>
 <li>Підтвердити оплату.</li>
 <li>Відповісти на ваші питання і дати відгук на вашу ретуш.</li>
 <li>Зрозуміти, які реклама й матеріали працюють: за мітками посилань і діями в боті.</li>
 <li>Зрідка написати про нові матеріали тим, хто вже користувався ботом. Слово «стоп»
     у будь-якому повідомленні боту вимикає такі розсилки.</li>
</ul>
<p>Дані не продаються і не передаються рекламним мережам чи іншим стороннім особам.</p>

<h2>Хто бачить і де зберігаються</h2>
<p>Ірина й адміністратор бота. Сервер і база даних працюють у Render, дата-центр у Франкфурті (ЄС).
Повідомлення доставляє Telegram, платежі обробляє Monobank, кожен за своїми правилами.</p>

<h2>Скільки зберігаємо</h2>
<p>Поки працює бот: куплене дає доступ назавжди, і запис про покупку цей доступ тримає.
Якщо бот припинить роботу, дані видаляються. Раніше видаляємо на ваш запит.</p>

<h2>Видалення даних</h2>
<p>Напишіть на <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>
з темою <b>Видалення даних</b> або напишіть боту «видаліть мої дані». Дані видаляються протягом
30 днів, підтвердження надсилається у відповідь. Після видалення бот не памʼятає ваших покупок,
тож доступ до них через бот зникає. Щоб бот просто більше не писав, досить його заблокувати.</p>

<h2>Застосунок Meta «iryna-reklama»</h2>
<p>Застосунок обслуговує рекламний кабінет і професійний акаунт Instagram
@iryna_rul_photographer, якими оператор керує за дорученням власниці акаунта. Публічної
реєстрації в ньому немає, стороннім людям він не доступний.</p>
<ul>
 <li>Які дані: статистика реклами (витрати, покази, кліки, розмови); повідомлення Instagram Direct
     і коментарі цього акаунта разом з імʼям співрозмовника, яке видно в самому листуванні;
     службові ідентифікатори сторінки, акаунта Instagram і рекламного кабінету.</li>
 <li>Навіщо: відповідати на звернення клієнток цього акаунта й оцінювати результативність реклами.
     Інших цілей немає.</li>
 <li>Де і скільки: на робочому компʼютері оператора і на сервері в Render (Франкфурт), доки
     триває робота з акаунтом; після її кінця дані видаляються. Видалення на запит так само,
     як для бота вище. Власниця акаунта може будь-коли відкликати доступ застосунку
     в налаштуваннях Meta, і обробка припиняється того ж дня.</li>
</ul>

<hr>

<h1 id="en">Privacy Policy</h1>
<div class="d">Telegram bot <code>@iryna_rul_bot</code>, course cabinet and Meta app
<code>iryna-reklama</code> &middot; updated 13 October 2026</div>

<h2>Whose bot this is</h2>
<p>The bot belongs to Iryna, a beauty and fashion photographer based in Kyiv and Zhytomyr
(Instagram <a href="https://www.instagram.com/iryna_rul_photographer/">@iryna_rul_photographer</a>).
She uses it to deliver her photography and retouching materials (free lessons, a guide and a course)
and to answer questions. The bot, its server and the Meta app are technically operated by
Yaroslav Kopchyk.</p>

<h2>Contacts</h2>
<ul>
 <li>Iryna: Instagram Direct
     <a href="https://www.instagram.com/iryna_rul_photographer/">@iryna_rul_photographer</a>
     or a message to the bot <a href="https://t.me/iryna_rul_bot">@iryna_rul_bot</a>.</li>
 <li>Data and technical questions: <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>
     (Yaroslav Kopchyk).</li>
</ul>

<h2>Data the bot collects</h2>
<ul>
 <li>Telegram profile: numeric ID, first name, last name and @username as set in your Telegram.
     The bot does not see or ask for your phone number.</li>
 <li>Where you came from: the label of the link you used to open the bot (for example, an ad or the channel).</li>
 <li>Time of your first visit and of your last action.</li>
 <li>What you do in the bot and the course cabinet: buttons pressed, materials received and opened,
     lessons watched.</li>
 <li>Messages you send to the bot (the first 300 characters are stored) and files you send.
     Iryna and the administrator see them in order to reply.</li>
 <li>Purchases: what was bought, order code, amount in UAH, time of payment and delivery. Payments go
     through Monobank; the bot sees only the amount, time, payment comment and the payer label
     in the statement. The bot never receives card details.</li>
 <li>Whether you are in Iryna's Telegram channel and whether you have blocked the bot.</li>
</ul>

<h2>Why</h2>
<ul>
 <li>To deliver the materials and course access you received or bought, and to keep that access.</li>
 <li>To confirm payments.</li>
 <li>To answer your questions and give feedback on your retouching.</li>
 <li>To understand which ads and materials work, from link labels and actions in the bot.</li>
 <li>To occasionally tell people who have used the bot about new materials. The word "stop"
     in any message to the bot turns these messages off.</li>
</ul>
<p>Data is not sold and is not shared with ad networks or any other third parties.</p>

<h2>Who sees it and where it is stored</h2>
<p>Iryna and the bot administrator. The server and database run on Render, data centre in
Frankfurt (EU). Messages are delivered by Telegram and payments are processed by Monobank,
each under its own terms.</p>

<h2>Retention</h2>
<p>For as long as the bot operates: purchases give lifetime access, and the purchase record is
what keeps that access. If the bot stops operating, the data is deleted. Earlier on request.</p>

<h2>Data deletion</h2>
<p>Email <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a>
with the subject <b>Data deletion</b>, or write "delete my data" to the bot. Data is deleted within
30 days and a confirmation is sent in reply. After deletion the bot no longer knows your purchases,
so access to them through the bot ends. To simply stop messages from the bot, block it.</p>

<h2>Meta app "iryna-reklama"</h2>
<p>The app serves one advertising account and the Instagram professional account
@iryna_rul_photographer, which the operator manages on behalf of the account owner. There is
no public sign-up and no access for third parties.</p>
<ul>
 <li>Data: advertising statistics (spend, impressions, clicks, conversations); Instagram Direct
     messages and comments of this account, including the sender name visible in the conversation
     itself; technical identifiers of the Page, Instagram account and ad account.</li>
 <li>Why: to answer enquiries from this account's clients and to measure advertising performance.
     No other purpose.</li>
 <li>Where and how long: on the operator's working computer and on the server at Render (Frankfurt),
     for as long as the work on the account continues; the data is deleted when it ends. Deletion on
     request works as for the bot above. The account owner can revoke the app's access in Meta
     settings at any time, which stops processing the same day.</li>
</ul>

</body></html>"""


@app.get("/privacy")
def privacy():
    """Політика конфіденційності бота, кабінету і застосунку Meta iryna-reklama
    (українською й англійською, 13.10). Meta вимагає публічну адресу для
    публікації застосунку, ця сторінка і є нею; водночас інструкція з видалення
    даних."""
    return PRYVATNIST, 200, {"Content-Type": "text/html; charset=utf-8"}


VYDALENNIA = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Видалення даних / Data deletion</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:720px;margin:2em auto;padding:0 1em}</style></head><body>
<h1>Видалення даних</h1>
<p>Щоб видалити дані, які бот <code>@iryna_rul_bot</code> і застосунок Meta <code>iryna-reklama</code>
зберігають про вас (зокрема листування в Instagram Direct з @iryna_rul_photographer),
напишіть на <a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a> з темою
<b>Видалення даних</b> і вкажіть свій нік в Instagram або Telegram, або напишіть боту «видаліть мої дані».
Дані видаляються протягом 30 днів, підтвердження надсилаємо у відповідь.
Повна політика: <a href="/privacy">/privacy</a>.</p>
<h1 id="en">Data deletion</h1>
<p>To delete the data that the bot <code>@iryna_rul_bot</code> and the Meta app <code>iryna-reklama</code>
keep about you (including Instagram Direct messages with @iryna_rul_photographer), email
<a href="mailto:essentialism.core@gmail.com">essentialism.core@gmail.com</a> with the subject
<b>Data deletion</b> and your Instagram or Telegram username, or write "delete my data" to the bot.
Data is deleted within 30 days and a confirmation is sent in reply.
Full policy: <a href="/privacy#en">/privacy</a>.</p>
</body></html>"""


@app.get("/data-deletion")
def data_deletion():
    """Інструкція з видалення даних для налаштувань застосунку Meta (18.10)."""
    return VYDALENNIA, 200, {"Content-Type": "text/html; charset=utf-8"}


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
            notify(text, uid=uid)
        if kind == "done" and lesson == RETUSH_LESSON_PART and uid not in staff_ids() and not quiet:
            try:
                if GIFT_FOR_SUB:
                    lesson_done_gift(uid, name)
                elif give_gift(uid, GIFT_DONE):
                    notify("Подарунок (три схеми світла) після уроку %s: %s" % (lesson, name), uid=uid)
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
    kb = {"inline_keyboard": [[{"text": ZAKRIP_BTN, "url": ZAKRIP_URL}]]}
    raw = m.get("text") or ""
    parts = raw.split(None, 1)
    body = parts[1] if len(parts) > 1 else ""
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
                "/zakrip на повідомлення з текстом. Кнопка «" + ZAKRIP_BTN + "» стане сама.")
    if not r.get("ok"):
        return _zakrip_err(r.get("description"))
    mid = (r.get("result") or {}).get("message_id")
    p = api_raw("pinChatMessage", chat_id=ZAKRIP_CHAT, message_id=mid, disable_notification=True)
    if not p.get("ok"):
        return ("Пост опубліковано (id " + str(mid) + "), але не закріплено. "
                + _zakrip_err(p.get("description")))
    return "Готово, id " + str(mid) + ": пост у " + ZAKRIP_CHAT + " з кнопкою «" + ZAKRIP_BTN + "», закріплено."


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


@app.get("/push1/" + SECRET)
def push1_page():
    """Розсилка push1 для очей, лише читання: ті самі числа, що /push1, поіменно хто куди і чому ні, тексти."""
    store.session_begin()
    try:
        return _pre(push1_summary(push1_segments(), push1_texts(), full=True))
    finally:
        store.session_end()


@app.get("/lyudy/" + SECRET)
def lyudy_page():
    """Люди з бази для очей (13.10), лише читання: зведення й картка на людину; ?md=1 те саме Markdown-текстом."""
    now = datetime.now(timezone.utc)
    store.session_begin()
    try:
        data = store.people_data()
    finally:
        store.session_end()
    md = request.args.get("md") == "1"
    if data is None:
        msg = "База " + ("не відповіла" if store.ON else "вимкнена (нема DATABASE_URL)") + ": людей не показую."
        return (msg, 200, {"Content-Type": "text/plain; charset=utf-8"}) if md else _pre(msg)
    rows = lyudy_rows(data, now)
    kan = kanal_many([r["id"] for r in rows])
    for r in rows:
        r["kanal"] = kan[r["id"]]
    if md:
        return lyudy_md(rows, now), 200, {"Content-Type": "text/markdown; charset=utf-8"}
    return lyudy_html(rows, now)


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
        s = str(p.get("text") or p) if isinstance(p, dict) else str(p)
        if isinstance(p, dict) and r.get("kind") == "staff_reply" and ("via" in p or "type" in p):
            # 14.10: відправка людині персоналом: [що, як, хто] текст
            s = "[" + ", ".join(str(p[k]) for k in ("type", "via", "by") if p.get(k) is not None) + "] " + str(p.get("text") or "")
        out.append("#" + str(r.get("id")) + "  " + str(r.get("created_at"))[:19] + "  " + str(r.get("user_id")) + "  " + str(r.get("kind"))
                   + "  " + html.escape(s[:300]).replace("\n", " / "))
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


# Відправка людині з ПК (14.10): той самий журнал, що reply і /do, без токена бота в руках сесії.
PC_KINDS = {"photo": ("sendPhoto", "фото"), "video": ("sendVideo", "відео"),
            "document": ("sendDocument", "документ"), "voice": ("sendVoice", "голосове"),
            "audio": ("sendAudio", "аудіо"), "animation": ("sendAnimation", "гіфка"),
            "video_note": ("sendVideoNote", "кружечок"), "sticker": ("sendSticker", "стікер")}
PC_EXT = {".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".mp4": "video", ".mov": "video",
          ".ogg": "voice", ".oga": "voice", ".opus": "voice", ".mp3": "audio", ".m4a": "audio",
          ".wav": "audio", ".gif": "animation"}
PC_NO_CAPTION = ("video_note", "sticker")


def _upload(method, field, chat_id, name, blob, caption=None, reply_markup=None):
    """Файл з диска ПК людині (multipart); 403 = позначка blocked, як в api_raw."""
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        j = requests.post(API + "/" + method, data=data, files={field: (name, blob)}, timeout=120).json()
    except Exception as e:
        return {"ok": False, "description": str(e)}
    if j.get("error_code") == 403:
        mark_blocked(chat_id, j.get("description"))
    return j


def _result_fid(res, kind):
    v = (res or {}).get(kind) if isinstance(res, dict) else None
    if isinstance(v, list):
        v = v[-1] if v else None
    return (v or {}).get("file_id") if isinstance(v, dict) else None


PC_KB = {"kanal": "кнопка каналу", "urok_kanal": "кнопки «Відкрити урок» і каналу", "hajd": "кнопка гайда"}
PC_MARKS = {"push1": PUSH_KEY, "hajd199": "hajd199", "post51": "post51"}   # mark -> префікс kv-ключа (16.10: hajd199
# для розсилки про гайд; 17.10: post51, пост каналу зі схемою світла непідписаним, кнопка каналу під фото)


def pc_kb(name):
    """Кнопки для /nadislaty за назвою (15.10): ті самі, що в push1: канал веде на інвайт push1 (PUSH1_URL),
    урок на урок 1.5 у кабінеті. None = такої назви нема чи нема KABINET_URL для урока."""
    t = push1_texts()
    if name == "kanal":
        return push1_kb(t, "")
    if name == "urok_kanal" and retush_lesson_url():
        return push1_kb(t, "G2")
    if name == "hajd":      # 16.10: розсилка про гайд 199: та сама кнопка, що в боті, відкриває картку гайда
        return {"inline_keyboard": [[{"text": TIERS["t1"]["btn"], "callback_data": "guide"}]]}
    return None


def pc_kb_view(kb):
    """Кнопки словами для dry: підпис, куди веде (url чи web_app)."""
    out = []
    for row in (kb or {}).get("inline_keyboard") or []:
        for b in row:
            out.append({"text": b.get("text"), "url": b.get("url") or (b.get("web_app") or {}).get("url"),
                        "web_app": bool(b.get("web_app"))})
    return out


@app.post("/nadislaty/" + SECRET)
def nadislaty():
    """
    Людині з ПК будь-що (слово Yaro 14.10: «будь-яке повідомлення легко людині надіслати без
    переписування всього бота і передеплоювання»). Поля (JSON, форма чи ?query): id, text, file_id
    або файл у полі file, kind (photo/video/document/voice/audio/animation/video_note/sticker; без нього
    з розширення файла, file_id = document), by (хто), dry=1 (лише показати кому, нічого не слати).
    Підпис під файлом, коли текст до 1024 і тип його має; інакше текст окремим повідомленням перед файлом.
    15.10: kb=kanal | urok_kanal додає під текст кнопки push1 (лише текст, без файлу); mark=push1 (лише з kb)
    ставить людині push1 так, ніби вона його отримала (kv push1:<id>, події push1 і для урока lesson_gift), щоб
    /push1 go їй не дублював; вдруге mark=push1 цій людині не шле. dry повертає кнопки з посиланнями.
    16.10: kb=hajd кнопка «Гайд, <ціна> грн» (callback guide, як у боті); mark=hajd199 (kv hajd199:<id>, подія hajd199)
    ставить, що розсилка про гайд людині була, вдруге не шле.
    Захищено секретом вебхука, як /zalyvka. Подія staff_reply via=pc. Відповідь JSON.
    """
    j = request.get_json(silent=True)
    j = j if isinstance(j, dict) else {}

    def arg(k):
        v = j.get(k)
        if v is None:
            v = request.form.get(k)
        if v is None:
            v = request.args.get(k)
        return str(v).strip() if v is not None else ""

    def out(code, **kw):
        return json.dumps(kw, ensure_ascii=False), code, {"Content-Type": "application/json; charset=utf-8"}

    sid = arg("id")
    if not sid.isdigit():
        return out(400, ok=False, error="потрібен id людини (число)")
    target = int(sid)
    text, fid, up = arg("text"), arg("file_id"), request.files.get("file")
    kind, by = arg("kind").lower(), arg("by") or "pc"
    if kind and kind not in PC_KINDS:
        return out(400, ok=False, error="kind: " + ", ".join(PC_KINDS))
    kbname, mark = arg("kb").lower(), arg("mark").lower()
    kb = None
    if kbname:
        kb = pc_kb(kbname)
        if not kb:
            return out(400, ok=False, error="kb: " + ", ".join(PC_KB) + " (урок потребує KABINET_URL)")
        if (fid or up or kind) and ((kind or "photo") in PC_NO_CAPTION or not text or len(text) > 1024):
            return out(400, ok=False, error="kb лише з текстом чи під файлом з підписом до 1024 знаків")
    if mark and (mark not in PC_MARKS or not kb):
        return out(400, ok=False, error="mark: " + " | ".join(PC_MARKS) + ", лише разом з kb")
    if mark and not store.ON:
        return out(503, ok=False, error="бази нема: без неї не знаю, кому push1 уже надіслано")
    _tm.person = None
    store.session_begin()
    try:
        name = person_name(target)
        pkey = PC_MARKS.get(mark, PUSH_KEY) + ":" + str(target)
        if arg("dry").lower() in ("1", "true", "yes"):
            err = None if name else "людина ще не писала боту (Telegram її не знає)"
            if not err and mark and store.kv_get(pkey):
                err = mark + " цій людині вже був (kv " + pkey + ": " + str(store.kv_get(pkey)) + ")"
            extra = {"kb": pc_kb_view(kb), "mark": mark or None} if kb else {}
            return out(200, ok=not err, dry=True, to=name, error=err, **extra)
        if mark and store.kv_get(pkey):
            return out(409, ok=False, to=name, error=mark + " цій людині вже був (kv " + pkey + ": "
                       + str(store.kv_get(pkey)) + "), вдруге не шлю")
        if not (text or fid or up):
            return out(400, ok=False, to=name, error="нема що слати: text, file_id чи file")
        if up and not kind:
            kind = PC_EXT.get(os.path.splitext(up.filename or "")[1].lower(), "document")
        kind = kind or "document"
        has_file = bool(up or fid)
        cap = text if has_file and text and len(text) <= 1024 and kind not in PC_NO_CAPTION else None
        sent, new_fid, err = [], None, None
        file_kb = kb if has_file and cap else None       # 17.10: кнопки під фото з підписом, одним повідомленням
        if text and not cap:
            if kbname == "urok_kanal":
                kabinet_mist.push_user(target)         # людина в базі кабінету до кнопки уроку, як у push1 G2
            r = api_raw("sendMessage", chat_id=target, text=text, reply_markup=kb, disable_web_page_preview=True)
            if r.get("ok"):
                sent.append("текст + " + PC_KB[kbname] if kb else "текст")
            else:
                err = _send_err(r)
        if has_file and not err:
            if up:
                blob, fname = up.read(), up.filename or "file"
                r = _upload(PC_KINDS[kind][0], kind, target, fname, blob, cap, file_kb)
                if not r.get("ok") and kind == "photo" and r.get("error_code") == 400:
                    kind = "document"      # фото не пройшло як фото (розмір, пропорції): шлемо файлом
                    r = _upload("sendDocument", kind, target, fname, blob, cap, file_kb)
            else:
                r = api_raw(PC_KINDS[kind][0], **{"chat_id": target, kind: fid, "caption": cap,
                                                  "reply_markup": file_kb})
            if r.get("ok"):
                sent.append(PC_KINDS[kind][1] + (" з підписом" if cap else "")
                            + (" + " + PC_KB[kbname] if file_kb else ""))
                new_fid = _result_fid(r.get("result"), kind)
            else:
                err = _send_err(r)
        if sent:
            _log_sent(target, by, "pc", " + ".join(sent), text)
            if mark in ("hajd199", "post51"):
                try:
                    store.kv_set(pkey, "ok " + kbname)
                    store.log_event(target, mark, {"kb": kbname, "ok": True, "via": "pc"})
                except Exception as e:
                    log.warning("mark %s %s: %s", mark, target, e)
            elif mark:
                seg = "G2" if kbname == "urok_kanal" else "INV"
                try:
                    store.kv_set(pkey, "ok " + seg)
                    if seg == "G2":
                        store.log_event(target, "lesson_gift", {"via": PUSH_KEY})
                    store.log_event(target, PUSH_KEY, {"seg": seg, "ok": True, "via": "pc"})
                except Exception as e:
                    log.warning("mark push1 %s: %s", target, e)
        log.info("З ПК -> %s: %s%s", target, " + ".join(sent) or "нічого", (", помилка: " + err) if err else "")
        return out(502 if err else 200, ok=not err, to=name, sent=sent, file_id=new_fid, error=err)
    finally:
        store.session_end()


@app.get("/ne_v_kanali/" + SECRET)
def ne_v_kanali():
    """
    Кому слати розсилку з кнопкою каналу (17.10, пост 51 непідписаним): клієнти з бази без персоналу,
    PUSH_SKIP_IDS, заблокованих бота і тих, хто писав «стоп»; ?mark=post51 прибирає тих, кому вже було.
    Кожному getChatMember: «ні» йде в to, «так» і «невідомо» окремо. Лише читання, JSON; слати /nadislaty.
    """
    mark = (request.args.get("mark") or "").strip().lower()
    if mark and mark not in PC_MARKS:
        return json.dumps({"ok": False, "error": "mark: " + " | ".join(PC_MARKS)}, ensure_ascii=False), 400
    store.session_begin()
    try:
        rows = store.push_rows() if store.ON else None
        if rows is None:
            return json.dumps({"ok": False, "error": "бази нема або не відповіла"}, ensure_ascii=False), 503
        staff = {i for i in [ADMIN_ID, IRA_ID] + NOTIFY_IDS + LEAD_IDS if i}
        pool, skip = [], {"персонал чи вручну": 0, "заблокували бота": 0, "писали «стоп»": 0, mark or "-": 0}
        for r in rows:
            uid, seen, blocked_at = r.get("user_id"), r.get("last_seen_at"), r.get("blocked_at")
            if uid in staff or uid in PUSH_SKIP_IDS or (r.get("role") or "client") != "client":
                skip["персонал чи вручну"] += 1
            elif blocked_at and not (seen and seen > blocked_at):
                skip["заблокували бота"] += 1
            elif PUSH_STOP_RE.search(r.get("texts") or ""):
                skip["писали «стоп»"] += 1
            elif mark and store.kv_get(PC_MARKS[mark] + ":" + str(uid)):
                skip[mark] += 1
            else:
                pool.append(r)
    finally:
        store.session_end()
    kan = kanal_many([r["user_id"] for r in pool])
    to, yes, unk = [], [], []
    for r in pool:
        st = kan[r["user_id"]]
        p = {"id": r["user_id"], "who": who({"id": r["user_id"], "username": r.get("username"),
                                             "first_name": r.get("first_name"), "last_name": r.get("last_name")})}
        (to if st[0] is False else yes if st[0] else unk).append(dict(p, why=st[1]) if st[0] is None else p)
    return json.dumps({"ok": True, "to": to, "v_kanali": len(yes), "nevidomo": unk, "skip": skip},
                      ensure_ascii=False), 200, {"Content-Type": "application/json; charset=utf-8"}


@app.get("/jars/" + SECRET)
def jars():
    """Рахунки Mono для MONO_JAR (19.10: картки, на які йде «За посиланням», і старі банки)."""
    if not MONO_TOKEN:
        return "MONO_TOKEN не заданий"
    try:
        r = requests.get(MONO + "/personal/client-info",
                         headers={"X-Token": MONO_TOKEN}, timeout=20)
        if r.status_code != 200:
            return "monobank: " + str(r.status_code)
        out = ["<pre>", "MONO_JAR зараз: " + (MONO_JAR[:6] + "…" if MONO_JAR else "порожній")]
        for a in (r.json().get("accounts") or []):
            out.append("картка " + ", ".join(x[-4:] for x in (a.get("maskedPan") or []))
                       + " " + str(a.get("type")) + "  id: " + str(a.get("id"))
                       + "  лінк: " + str(a.get("sendId")))
        for j in (r.json().get("jars") or []):
            out.append(str(j.get("title")) + "  id: " + str(j.get("id")) + "  лінк: " + str(j.get("sendId")))
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


# ---------- автовідповідь в Instagram Direct (18.10) ----------
# Власна заміна ManyChat: людині з реклами одна відповідь з посиланням у бота.
# Працює лише з IG_VERIFY_TOKEN, META_APP_SECRET і IG_PAGE_TOKEN; без них вимкнено.
# Читати й писати чужим людям Meta дає лише з Advanced access instagram_manage_messages.
IG_VERIFY_TOKEN = os.getenv("IG_VERIFY_TOKEN", "").strip()
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()
IG_PAGE_TOKEN = os.getenv("IG_PAGE_TOKEN", "").strip()
IG_ADS = {"52535499581237": "A", "52535495609037": "B", "52536319850037": "C"}   # 21.10: C = SHEMA2-CHORNYI (UA), мітка shema2
IG_REPLY_A = "Привіт ♥️ Це Іра. Мій безкоштовний файл «3 схеми світла з одного сетапу» тут: https://t.me/iryna_rul_bot?start=svitlo"
IG_REPLY_B = "Привіт ♥️ Це Іра. Гайд «Світло»: 13 моїх схем з імпульсним світлом, 299 грн замість 900. Тут: https://t.me/iryna_rul_bot?start=hajd299"
IG_REPLY_C = IG_REPLY_A.replace("start=svitlo", "start=shema2")
IG_REPLY_K = IG_REPLY_A.replace("start=svitlo", "start=koment")   # 21.10 (Yaro): коментар «схема» під відео → лінк у Direct
IG_REPLIES = {"A": IG_REPLY_A, "B": IG_REPLY_B, "C": IG_REPLY_C, "K": IG_REPLY_K}
IG_USER_ID = "17841421469087917"   # @iryna_rul_photographer (бізнес-акаунт сторінки Iryna rul)
IG_PAGE_ID = "1159407250599020"    # сторінка Iryna rul
_IG_RE_KOMENT = re.compile(r"схем", re.I)   # 21.10 (Yaro): «коли в коментарях пишуть схема»
_IG_RE_A = re.compile(r"(3|три)\s*схем|схем\w*\s+світла|^\W*схеми\W*$", re.I)   # 21.10: голе «СХЕМИ» з реклами shema2
_IG_RE_B = re.compile(r"гайд", re.I)
# стандартна фраза Instagram, коли людина пише з рілса чи сторіз реклами (шаблон там не показується)
_IG_RE_REKLAMA = re.compile(r"дізнатися\s+більше|узнать\s+(об\s+этом\s+)?подробнее|learn\s+more|more\s+info", re.I)


def ig_on():
    return bool(IG_VERIFY_TOKEN and META_APP_SECRET and IG_PAGE_TOKEN)


def ig_sig_ok(raw, header):
    """X-Hub-Signature-256: sha256=<hmac тіла ключем секрету додатка>."""
    if not META_APP_SECRET or not header or not header.startswith("sha256="):
        return False
    good = hmac.new(META_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, header[7:])


def ig_which(text, ad_id):
    """'A', 'B' або None. Слова людини важать більше за оголошення."""
    t = text or ""
    if _IG_RE_A.search(t):
        return "C" if IG_ADS.get(str(ad_id or "")) == "C" else "A"
    if _IG_RE_B.search(t):
        return "B"
    if str(ad_id or "") in IG_ADS:
        return IG_ADS[str(ad_id)]
    # фраза з реклами без відомого ad_id: головне оголошення А
    return "A" if _IG_RE_REKLAMA.search(t) else None


def _ig_ad_id(m):
    msg = m.get("message") or {}
    for r in (msg.get("referral"), m.get("referral"),
              ((msg.get("reply_to") or {}).get("ad") if isinstance(msg.get("reply_to"), dict) else None)):
        if isinstance(r, dict):
            a = r.get("ad_id") or r.get("id")
            if a:
                return str(a)
    return None


def ig_send(ig_id, text, comment_id=None):
    """Відповідь у Direct. comment_id = приватна відповідь на коментар (Meta: один раз на коментар, до 7 днів)."""
    to = {"comment_id": comment_id} if comment_id else {"id": ig_id}
    r = requests.post("https://graph.facebook.com/v21.0/me/messages",
                      params={"access_token": IG_PAGE_TOKEN},
                      json={"recipient": to, "message": {"text": text}}, timeout=15)
    if r.status_code != 200:
        log.warning("ig_send %s: %s", r.status_code, r.text[:300])
    return r.status_code == 200


def _ig_komentari(d):
    """Коментарі з вебхука (object instagram, entry[].changes[] field comments)."""
    out = []
    for e in d.get("entry") or []:
        for ch in e.get("changes") or []:
            if ch.get("field") != "comments":
                continue
            v = ch.get("value") or {}
            out.append({"id": v.get("id"), "from": str((v.get("from") or {}).get("id") or ""),
                        "text": v.get("text") or "", "media": (v.get("media") or {}).get("id")})
    return out


@app.get("/ig-subscribe/" + SECRET)
def ig_subscribe():
    """Підписати сторінку Іри на вебхук застосунку (потрібен IG_PAGE_TOKEN з pages_manage_metadata)."""
    if not IG_PAGE_TOKEN:
        return {"ok": False, "err": "nema IG_PAGE_TOKEN"}, 200
    r = requests.post("https://graph.facebook.com/v21.0/%s/subscribed_apps" % IG_PAGE_ID,
                      params={"access_token": IG_PAGE_TOKEN,
                              "subscribed_fields": "messages,messaging_postbacks,messaging_referral,feed"}, timeout=15)
    return {"status": r.status_code, "body": r.text[:500]}, 200


@app.get("/ig-webhook")
def ig_verify():
    if IG_VERIFY_TOKEN and request.args.get("hub.mode") == "subscribe" and \
       request.args.get("hub.verify_token") == IG_VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "ni", 403


@app.post("/ig-webhook")
def ig_webhook():
    if not ig_on():
        return {"ok": False, "err": "vymkneno"}, 200
    raw = request.get_data()
    if not ig_sig_ok(raw, request.headers.get("X-Hub-Signature-256", "")):
        return "ni", 403
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        return {"ok": False}, 200
    sent = 0
    store.session_begin()
    try:
        for z in _rozgornuty_meta(d):
            if z["is_echo"] or not z["ig_id"]:
                continue
            try:
                cid = store.dm_contact(z["ig_id"])
                store.dm_event(cid, "in", body=z["text"], kind=z["kind"],
                               payload=z["_syre"], ext_id=z["mid"])
            except Exception as e:
                log.warning("ig_webhook запис: %s", e)
            which = ig_which(z["text"], _ig_ad_id(z["_syre"]))
            # одна автовідповідь на людину назавжди; без бази kv_claim дає False
            if which and store.kv_claim("ig_auto:" + z["ig_id"]):
                if ig_send(z["ig_id"], IG_REPLIES[which]):
                    sent += 1
                    store.log_event(None, "ig_auto", {"ig": z["ig_id"], "v": which})
        # 21.10 (Yaro): коментар зі «схем…» під відео → одна приватна відповідь у Direct з лінком koment
        for k in _ig_komentari(d):
            if not k["id"] or k["from"] in ("", IG_USER_ID) or not _IG_RE_KOMENT.search(k["text"]):
                continue
            if store.kv_claim("ig_kom:" + k["from"]):
                if ig_send(None, IG_REPLY_K, comment_id=k["id"]):
                    sent += 1
                    store.log_event(None, "ig_auto", {"ig": k["from"], "v": "K", "media": k["media"]})
        return {"ok": True, "sent": sent}, 200
    except Exception as e:
        log.warning("ig_webhook впав: %s", e)
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
_LOCKED_CB = ("les:", "my:guide", "moi", "magnet", "give:", "paid:", "lock:", "sub:check", "zapr:open")
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
            # Постійна клавіатура «Мої матеріали» + «Канал «для своїх»» (13.10): кожен приватний /start
            # (з видаленим чатом зникає і клавіатура) і перше повідомлення людини без прапорця pkb2:<id>
            # отримують її рівно раз, у кінці апдейту (pkb_finish). Натиснута кнопка каналу = нова клавіатура
            # вже є; «Мої матеріали» є і в старій, тож її натискання нічого не доводить. Не Ірі.
            if (m.get("chat") or {}).get("type") == "private" and chat_id == uid and uid != IRA_ID:
                if text == KANAL_BTN:
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
            # Особиста ціна курсу (19.10): /tsina <id> <грн>, з нового рядка текст картки. Людині йде цей текст,
            # кнопка оплати на цю суму; оплату на цю суму handle_tx звіряє і видає курс сам (kv tsina:).
            if uid in NOTIFY_IDS and text.split()[:1] and text.split()[0].split("@")[0] == "/tsina":
                _head, _, _body = text.partition("\n")
                _parts = _head.split() + ["", ""]
                if not (_parts[1].isdigit() and _parts[2].isdigit() and _body.strip()):
                    send(chat_id, "Напишіть так: /tsina 897646290 2500\nтекст картки з нового рядка")
                    return "ok"
                target, uah = int(_parts[1]), int(_parts[2])
                store.kv_set("tsina:" + str(target), str(uah))
                code = order_code(target, "k12z")
                store.add_purchase(target, "course", tier="k12z", order_code=code, amount_uah=uah)
                store.log_event(target, "tier_pick", {"tier": "k12z", "code": code, "tsina": uah})
                # 19.10, слово Yaro: людині нічого не вписувати
                body = _body.strip()
                tu = store.get_user(target) or {}
                name = who({"id": target, "username": tu.get("username"),
                            "first_name": tu.get("first_name"), "last_name": tu.get("last_name")})
                ok = send(target, body, pay_kb("k12z", target))
                send(chat_id, ("Надіслано: " if ok else "Не дійшло: ") + name + ", " + str(uah) + " грн, код " + code)
                return "ok"
            # Подарунок схем вручну (14.10): /podarunok <id> шле тим самим give_gift текст GIFT_HAND і PDF магніту
            # з кнопкою каналу; раз назавжди (kv gift:<id>), схеми вже видані чи заявка зайнята = нічого не шле.
            if uid in NOTIFY_IDS and text.split()[:1] and text.split()[0].split("@")[0] == "/podarunok":
                _arg = (text.split() + [""])[1]
                if not _arg.isdigit():
                    send(chat_id, "Напишіть так: /podarunok 2033627806 (id людини зі сповіщення «Новий у боті»)")
                    return "ok"
                podarunok_staff(chat_id, int(_arg))
                return "ok"
            # Відповідь людині будь-чим (14.10): /do <id> (чи /do reply-ем на сповіщення) = наступне
            # повідомлення піде цій людині; /skasuvaty знімає режим. Лише NOTIFY_IDS і адмін; у людини
            # /do лишається звичайним текстом (CLIENT_TEXT нижче).
            _cmd = text.split()[0].split("@")[0] if text.split() else ""
            if staff_cmd(uid) and _cmd == "/do":
                _arg = (text.split() + [""])[1]
                _rt = (fb_target(dict(m["reply_to_message"], _chat=chat_id), uid)
                       if m.get("reply_to_message") and not _arg else None)
                if _arg.isdigit() or _rt:
                    do_start(chat_id, uid, int(_arg) if _arg.isdigit() else _rt, m.get("message_id"))
                else:
                    _staff_say(chat_id, "Напишіть так: /do 458676312 (id людини зі сповіщення), "
                               "або кнопка «Написати» під сповіщенням.", m.get("message_id"))
                return "ok"
            if staff_cmd(uid) and _cmd == "/skasuvaty":
                _t, _exp = do_get(uid)
                do_clear(uid)
                _staff_say(chat_id, ("Скасовано: " + (person_name(_t) or "id %s" % _t) + " нічого не отримає.")
                           if _t else "Режиму /do не було, нічого не скасовано.", m.get("message_id"))
                return "ok"
            # Посилання МК (13.10): /mk скільки видано і чи відкрите, /mk stop закрити, /mk start відкрити.
            if uid in NOTIFY_IDS and text.split()[:1] and text.split()[0].split("@")[0] == "/mk":
                _arg = (text.split() + [""])[1].lower()
                if MK_CODE and _arg in ("stop", "start"):
                    store.kv_set("mk_off:" + MK_CODE, "1" if _arg == "stop" else "")
                send(chat_id, mk_status())
                return "ok"
            # Розсилка push1 (13.10): /push1 перегляд лише тому, хто питає (не всім NOTIFY_IDS); /push1 go шле людям.
            if uid in NOTIFY_IDS and text.split()[:1] and text.split()[0].split("@")[0] == "/push1":
                if (text.split() + [""])[1].lower() == "go":
                    store.log_event(uid, "push1_go", {})
                    send(uid, push1_go(uid))
                else:
                    push1_preview(uid)
                return "ok"
            if uid == ADMIN_ID and text.startswith("/nova"):
                store.wipe_user(uid)
                _pkb_done.discard(uid)
                send(chat_id, "Чисто. Видали цей чат і зайди в бота заново, побачиш його як нова людина.")
                return "ok"

            # Відповідь Іри чи адміна reply-ем на переслане/сповіщення (чи в режимі /do) іде людині
            # будь-чим (14.10), раніше за матеріали Іри, щоб відповідь не потрапила в take_material.
            if ((uid in staff_ids() or staff_cmd(uid)) and not text.startswith("/")
                    and staff_route(m, chat_id, uid)):
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

            # Кнопка каналу з постійної клавіатури (13.10): рядок Іри й інлайн-кнопка в канал. Персоналу не
            # пересилаємо (це не повідомлення людини), подія kanal_btn.
            if text == KANAL_BTN and (m.get("chat") or {}).get("type") == "private":
                store.touch_user(u)
                store.log_event(uid, "kanal_btn")
                send(chat_id, KANAL_BTN_TEXT, {"inline_keyboard": [[{"text": KANAL_BTN, "url": kanal_btn_url()}]]})
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
                               give_kb(uid, "k12", "Видати курс вручну") if src in ("retush", "kurs", "kurs10") else None,
                               uid=uid)
                bg(_start_after)
                if src == "guide":
                    bg(store.log_event, uid, "guide_entry", {"tag": src})
                    send_card(chat_id, START_PIC, GUIDE_HELLO if courses_sale() else GUIDE_HELLO_NOC, guide_kb())
                elif src == "retush" and not FREE_LESSON and courses_sale():
                    bg(store.log_event, uid, "retush_entry", {"tag": src})
                    pick_product(chat_id, uid, u, "k12", gate=False)
                elif src == "retush":
                    # лід-магніт ретуші 08.10: урок 1.5 безкоштовно в кабінеті, без світла і без ціни
                    bg(store.log_event, uid, "retush_entry", {"tag": src})
                    send_card_file(chat_id, "static/retush-masky.png", RETUSH_MAGNET_HELLO, retush_magnet_kb())  # обкладинка магніту, без «Студійне світло»
                    kabinet_mist.push_user(uid)   # людина в базі кабінету одразу
                elif src == PRESET_TAG:
                    bg(store.log_event, uid, "preset_entry", {"tag": src})
                    give_preset(chat_id)
                elif src in SVITLO_TAGS:
                    # 16.10: реклама (svitlo) і шапка Instagram (profil): привіт про три схеми, «Канал» + «Я підписалась»,
                    # файл після sub:check; без уроку ретуші і ціни, далі Д2 (гайд 199) як у тих, хто має подарунок
                    bg(store.log_event, uid, "svitlo_entry", {"tag": src})
                    send_card(chat_id, START_PIC, SVITLO_HELLOS[src], svitlo_kb(src))
                elif src == HAJD_TAG:
                    bg(store.log_event, uid, "guide_entry", {"tag": src})
                    if not GUIDE_SALE:
                        send_paused(chat_id)
                    else:
                        kb = tiers_kb()
                        send_card(chat_id, CARD_GUIDE, guide_intro(kb), kb)
                elif src == "mk":
                    # мітка закріпу каналу (20.10): коротке привітання і «Дізнатися детальніше»;
                    # картка з кнопкою заявки лише після цього натиску (callback mk)
                    bg(store.log_event, uid, "mk_entry", {"tag": src})
                    send(chat_id, MK_HELLO, mk_hello_kb())
                elif src.startswith("mk_"):
                    mk_start(chat_id, uid, u, src[3:])
                elif src in ("kurs", "kurs10") and course_owner_reply(chat_id, uid):
                    bg(store.log_event, uid, "kurs_entry", {"tag": src})
                elif src == "kurs10" and courses_sale():
                    # лід з діректу 08.10: курс зі знижкою 10 %, оплата на знижену суму
                    bg(store.log_event, uid, "kurs_entry", {"tag": src})
                    pick_product(chat_id, uid, u, "k12z", gate=False)
                elif src == "kurs" and courses_sale():
                    # мітка з кабінету: одразу пропозиція курсу, без вітання з магнітом
                    bg(store.log_event, uid, "kurs_entry", {"tag": src})
                    if COURSE_BUNDLE_ONLY:
                        pick_product(chat_id, uid, u, "k12", gate=False)
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
                    pick_product(chat_id, uid, u, "k12", gate=False)
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
                        notify_lead("Питають про ЗЙОМКУ: " + who(u), uid=uid)
            else:
                store.touch_user(u)
                store.log_event(uid, "message", {"text": text[:300]})
                if not is_file:
                    ntext = "Повідомлення в боті від " + who(u) + ":\n" + (text or "[не текст]")
                    notify(ntext, uid=uid)
                    if IRA_ID and IRA_ID not in NOTIFY_IDS:
                        _staff_send([IRA_ID], ntext, uid=uid)
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

            if (data == "magnet" or data in LEGACY_LOCK_DATA) and GIFT_FOR_SUB:
                # п.1: «Забрати три схеми світла» тим самим шляхом, що «Я підписалась»:
                # у каналі файл (раз назавжди), ні: Т2 з кнопками канал і «Я підписалась».
                store.log_event(uid, "magnet_ask", {"legacy": data} if data != "magnet" else None)
                sub_check(chat_id, uid, u)
            elif data == "magnet" or data in LEGACY_LOCK_DATA:
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
            elif data == "sub:check":
                sub_check(chat_id, uid, u)
            elif data == "zapr:open":
                # п.6: людина сама попросила про курс, з цього моменту бачить картку з ціною
                if store.kv_claim("zapr:" + str(uid)):
                    store.log_event(uid, "zapr_open")
                if not course_owner_reply(chat_id, uid):
                    pick_product(chat_id, uid, u, "k12", gate=False)
            elif data == "mk":
                store.log_event(uid, "mk_open")
                send_card(chat_id, CARD_MK, MK_TEXT, mk_kb())
            elif data == "mk:want":
                store.log_event(uid, "mk_want")
                send(chat_id, MK_THANKS, {"inline_keyboard": channel_rows()} if CHANNEL_URL else None)
                if lead_once(uid, "mk"):
                    notify_lead("ЗАЯВКА НА МК: " + who(u) + "\nНаписати особисто.", uid=uid)
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
            elif data.startswith("noget:") and claim_nechyia(uid, data.split(":")[1]):
                store.log_event(uid, "noget_claimed", {"tier": data.split(":")[1]})
            elif data.startswith("noget:"):
                key = data.split(":")[1]
                code = order_code(uid, key)
                send(chat_id, NOGET_TEXT)
                store.log_event(uid, "noget", {"code": code})
                if lead_once(uid, "noget:" + key):
                    notify("КАЖЕ, ЩО ОПЛАТИВ, А ФАЙЛУ НЕМАЄ\n" + pname(key) + "\n" + who(u)
                           + "\nКод: " + code, give_kb(uid, key), uid=uid)
            elif data.startswith("paid:") and TEST_MODE and uid in NOTIFY_IDS:
                key = data.split(":")[1]
                code = order_code(uid, key)
                ok = deliver(uid, key)
                if not ok:
                    send(chat_id, BROKEN_FILE_TEXT)
                    notify("ФАЙЛ НЕ ВИДАВСЯ. " + pname(key) + ": " + ready_text(key)
                           + "\n" + who(u), uid=uid)
                store.mark_paid(code)
                if ok:
                    store.mark_delivered(code)
                store.log_event(uid, "pay_test", {"tier": key, "ok": ok})
                kabinet_mist.push_user(uid)
                notify("ТЕСТ оплати: " + pname(key) + "\n" + who(u), uid=uid)
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
            elif data.startswith("napys:") and staff_cmd(uid) and data[6:].isdigit():
                # кнопка «Написати» під сповіщенням: той самий режим, що /do <id>
                do_start(chat_id, uid, int(data[6:]), cq["message"].get("message_id"))
            elif data.startswith("podar:") and staff_cmd(uid) and data[6:].isdigit():
                # кнопка «🎁 Подарунок»: той самий give_gift, що /podarunok (раз назавжди)
                podarunok_staff(chat_id, int(data[6:]), cq["message"].get("message_id"))
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
_OPYS_RETUSH = ("Привіт, я Іра ❤️ Бʼюті і фешн фотограф, знімаю вже 7 років.\n\n"
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
        try:
            album_flush_all()          # зібраний альбом персоналу людині не губимо (14.10)
        except Exception as e:
            log.warning("poll: альбоми при зупинці: %s", e)
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
