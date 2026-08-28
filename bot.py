#!/usr/bin/env python3
"""
Бот Iryna Rul. Три речі й нічого більше.

1. Лійка: магніт, три пакети гайду, оплата в банку Monobank, видача файлу.
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
    "Хочете всі схеми, а не три, тисніть другу кнопку."
)
GUIDE_INTRO = (
    "Повний гайд «Світло» ♥️\n\n"
    "Усі мої робочі схеми, від чистої комерції до кольору.\n"
    "Кожна з розстановкою, налаштуваннями і кадром зі зйомки.\n\n"
    "Три варіанти, оберіть свій."
)
NOGET_TEXT = ("Перевірю вручну, зазвичай це кілька хвилин ♥️ "
              "Файл прийде сюди, нічого робити не треба.")
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

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CODE_RE = re.compile(r"IR([0-9A-Z]+)-([123])", re.I)


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


def api(method, **params):
    params = {k: v for k, v in params.items() if v is not None}
    try:
        r = requests.post(API + "/" + method, json=params, timeout=20)
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
    return {"inline_keyboard": rows}


def tiers_kb():
    return {"inline_keyboard": [[{"text": TIERS[k]["btn"], "callback_data": k}]
                                for k in ("t1", "t2", "t3")]}


def pay_kb(tier):
    rows = []
    if PAY_URL:
        rows.append([{"text": "Перейти до оплати", "url": PAY_URL}])
    if TEST_MODE:
        rows.append([{"text": "Я оплатив (тест)", "callback_data": "paid:" + tier}])
    # Найдорожчий глухий кут лійки: людина заплатила, а файл не прийшов.
    rows.append([{"text": "Оплатив, а файлу немає", "callback_data": "noget:" + tier}])
    return {"inline_keyboard": rows}


def give_kb(uid, tier):
    return {"inline_keyboard": [[{"text": "Видати гайд вручну",
                                  "callback_data": "give:" + str(uid) + ":" + tier}]]}


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
    return True


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
               "Впізнай по імені і видай гайд вручну.")
        return
    try:
        uid = unb36(m.group(1).upper())
    except Exception:
        return
    tier = "t" + m.group(2)
    code = "IR" + m.group(1).upper() + "-" + m.group(2)
    need = TIERS.get(tier, {}).get("uah", 0) * 100
    if amount < need * 0.9:
        store.log_event(uid, "pay_short", {"code": code, "uah": amount // 100})
        notify("Оплата " + str(amount // 100) + " грн за кодом " + code
               + ", а треба " + str(need // 100) + " грн. Гайд не видано.")
        return
    store.mark_paid(code, amount // 100)
    ok = give_guide(uid, tier)
    if ok:
        store.mark_delivered(code)
    store.log_event(uid, "pay_ok" if ok else "pay_undelivered", {"code": code})
    notify(("Оплата " + str(amount // 100) + " грн, код " + code + ". Гайд видано автоматично.")
           if ok else ("Оплата " + str(amount // 100) + " грн, код " + code
                       + ", але файл не пішов. Перевір GUIDE_FILE_ID."))


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
                     + " · оплат " + str(paid.get("n", 0)) + " на "
                     + str(paid.get("uah", 0)) + " грн")
        lines.append("Матеріалів від Іри: " + str(store.inbox_count()))
    return "\n".join(lines)


def send_file(chat_id, name, blob, caption=None):
    try:
        r = requests.post(API + "/sendDocument",
                          data={"chat_id": chat_id, "caption": caption or ""},
                          files={"document": (name, blob)}, timeout=60)
        return bool(r.json().get("ok"))
    except Exception as e:
        log.warning("sendDocument: %s", e)
        return False


# ---------- маршрути ----------

@app.get("/")
def health():
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
    return "<pre>url: %s\nу черзі: %s\nостання помилка: %s</pre>" % (
        i.get("url") or "ПОРОЖНЬО", i.get("pending_update_count", "?"),
        i.get("last_error_message") or "немає")


@app.get("/db/" + SECRET)
def db_status():
    return "<pre>" + status_text() + "</pre>"


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


@app.post("/upload/" + SECRET)
def upload():
    """
    Тимчасовий маршрут: приймає файл і віддає його telegram file_id.

    Навіщо. Щоб покласти гайд у бота, потрібен токен, а він живе тільки тут,
    у рантаймі. Репозиторій публічний, тому класти платний файл поруч з кодом
    не можна: він назавжди лишиться в історії. Браузер теж не підходить,
    бо вибір файлу в Telegram Web це системний діалог Windows.
    Тому файл заливається прямо сюди і одразу перетворюється на file_id.
    """
    f = request.files.get("file")
    if not f:
        return "немає файлу в полі file", 400
    try:
        r = requests.post(API + "/sendDocument",
                          data={"chat_id": ADMIN_ID, "caption": "Файл для GUIDE_FILE_ID"},
                          files={"document": (f.filename, f.stream)}, timeout=180)
        j = r.json()
        if not j.get("ok"):
            return "telegram: " + str(j.get("description")), 502
        doc = (j.get("result") or {}).get("document") or {}
        return "file_id: " + str(doc.get("file_id")) + "\nрозмір: " + str(doc.get("file_size"))
    except Exception as e:
        return "помилка: " + str(e), 500


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
                doc = m.get("document")
                if doc:
                    send(chat_id, "file_id цього файлу:\n" + doc.get("file_id", "?"))
                    return "ok"

            # Іра: кидає що завгодно, бот приймає і мовчить.
            if uid == IRA_ID and IRA_ON:
                store.touch_user(u, role="ira")
                if text.startswith("/start"):
                    send(chat_id, IRA_HELLO)
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
            elif data in TIERS:
                t = TIERS[data]
                code = order_code(uid, data)
                store.add_purchase(uid, "guide", tier=data, order_code=code, amount_uah=t["uah"])
                store.log_event(uid, "tier_pick", {"tier": data, "code": code})
                body = t["text"] + "\n\nПризначення платежу, впишіть його дослівно:\n" + code
                if PAY_URL:
                    body += "\n\nФайл прийде сюди сам, зазвичай за хвилину після оплати."
                else:
                    body += "\n\nРеквізити надішлю сюди найближчим часом ♥️ Заявку вже бачу."
                send(chat_id, body, pay_kb(data))
                notify("ЗАЯВКА: " + t["name"] + "\n" + who(u) + "\nКод: " + code,
                       give_kb(uid, data))
            elif data.startswith("noget:"):
                tier = data.split(":")[1]
                code = order_code(uid, tier)
                send(chat_id, NOGET_TEXT)
                store.log_event(uid, "noget", {"code": code})
                notify("КАЖЕ, ЩО ОПЛАТИВ, А ФАЙЛУ НЕМАЄ\n"
                       + TIERS.get(tier, {}).get("name", tier) + "\n" + who(u)
                       + "\nКод: " + code, give_kb(uid, tier))
            elif data.startswith("paid:") and TEST_MODE:
                tier = data.split(":")[1]
                code = order_code(uid, tier)
                ok = give_guide(uid, tier)
                if not ok:
                    send(chat_id, BROKEN_FILE_TEXT)
                    notify("ФАЙЛ НЕ ВИДАВСЯ, перевір GUIDE_FILE_ID\n" + who(u))
                store.mark_paid(code)
                if ok:
                    store.mark_delivered(code)
                store.log_event(uid, "pay_test", {"tier": tier, "ok": ok})
                notify("ТЕСТ оплати: " + TIERS.get(tier, {}).get("name", tier) + "\n" + who(u))
            elif data.startswith("give:") and uid in NOTIFY_IDS:
                parts = (data.split(":") + ["", ""])[:3]
                target = int(parts[1])
                ok = give_guide(target, parts[2])
                if ok and parts[2]:
                    code = order_code(target, parts[2])
                    store.mark_paid(code)
                    store.mark_delivered(code)
                store.log_event(target, "give_manual", {"by": uid, "ok": ok})
                send(chat_id, "Видано" if ok else "Не вдалося, перевір GUIDE_FILE_ID")
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
    except Exception as e:
        log.warning("ensure_webhook: %s", e)


if os.getenv("NO_THREADS", "").strip() != "1":
    threading.Thread(target=ensure_webhook, daemon=True).start()
    threading.Thread(target=mono_poll, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
