#!/usr/bin/env python3
"""
Міст баз (02.10.2026): бот штовхає людей і покупки в кабінет курсів.

Кабінет має свою базу (Render Postgres) і рахує доступ з копій таблиць бота
users і purchases. Бот джерело правди: після оплати, видачі, магніта чи гайда
шле людину і всі її покупки на POST <KABINET_URL>/internal/sync, а раз на
годину (і на старті) звіряє все: усі paid/delivered покупки, їхніх людей і
тих, хто має магніт чи гайд, пачками.

Правило номер один: без KABINET_URL і KABINET_KEY міст вимкнений повністю,
жодного потоку, запиту чи рядка в лозі: бот працює байт у байт як до мосту.
Правило номер два: будь-яка помилка лише в лог. Усе йде у фонових потоках,
відповідь людині не чекає кабінет; кабінет на безкоштовному Render спить
і прокидається до хвилини, тому тайм-аут довгий і три спроби з паузою.
"""

import os, time, logging, threading
from datetime import datetime

import requests

import store

log = logging.getLogger("kabinet_mist")

URL = os.getenv("KABINET_URL", "").strip().rstrip("/")
KEY = os.getenv("KABINET_KEY", "").strip()
ON = bool(URL and KEY)

TRIES = 3
PAUSE_S = (20, 40)              # між спробами: кабінет прокидається до хвилини
TIMEOUT = (10, 75)              # зʼєднання, відповідь
BATCH = 200
try:
    ZVIRKA_S = max(60, int(os.getenv("KABINET_ZVIRKA_S", "") or 3600))
except ValueError:
    ZVIRKA_S = 3600
START_DELAY_S = 30              # звірка на старті не заважає вебхуку

USER_FIELDS = ("user_id", "username", "first_name", "last_name", "role", "source_tag",
               "created_at", "last_seen_at", "got_magnet_at", "got_guide_at")
PURCHASE_FIELDS = ("order_code", "user_id", "product", "tier", "amount_uah", "status",
                   "source_tag", "slots_total", "slots_used", "created_at", "paid_at",
                   "delivered_at")

_zvirka_lock = threading.Lock()
_sleep = time.sleep             # тести підміняють


def _val(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _pick(row, fields):
    return {k: _val(row[k]) for k in fields if k in row}


def user_row(u):
    return _pick(u, USER_FIELDS)


def purchase_row(p):
    return _pick(p, PURCHASE_FIELDS)


def post(body):
    """Одна пачка в кабінет, до TRIES спроб. True, якщо кабінет прийняв."""
    if not ON:
        return False
    for i in range(TRIES):
        try:
            r = requests.post(URL + "/internal/sync", json=body,
                              headers={"X-Internal-Key": KEY}, timeout=TIMEOUT)
            code = getattr(r, "status_code", 0)
            if code == 200:
                return True
            if code in (400, 403):      # повтор не допоможе
                log.warning("кабінет відмовив: %s", code)
                return False
            log.warning("кабінет відповів %s, спроба %d", code, i + 1)
        except Exception as e:
            log.warning("кабінет недоступний, спроба %d: %s", i + 1, type(e).__name__)
        if i < TRIES - 1:
            _sleep(PAUSE_S[min(i, len(PAUSE_S) - 1)])
    return False


def _push_user_now(uid):
    try:
        u = store.get_user(uid)
        ps = store.purchases_of(uid, only_paid=False) or []
        body = {"users": [user_row(u)] if u else [],
                "purchases": [purchase_row(p) for p in ps if p.get("order_code")]}
        if body["users"] or body["purchases"]:
            post(body)
    except Exception as e:
        log.warning("міст: людина %s не пішла: %s", uid, e)


def push_user(uid):
    """Після mark_paid/mark_delivered/mark_magnet/mark_guide. Не чекає, не падає."""
    if not ON or not uid:
        return None
    try:
        t = threading.Thread(target=_push_user_now, args=(uid,), daemon=True)
        t.start()
        return t
    except Exception as e:
        log.warning("міст: потік не стартував: %s", e)
        return None


def zvirka():
    """Усі paid/delivered покупки, їхні люди і люди з магнітом чи гайдом, пачками.
    Повертає кількість прийнятих пачок або None, якщо звірка вже йде."""
    if not ON:
        return None
    if not _zvirka_lock.acquire(blocking=False):
        return None
    try:
        ps = store.q("""select * from purchases where status in ('paid', 'delivered')
                        and order_code is not null order by id""", fetch="all") or []
        us = store.q("""select * from users where got_magnet_at is not null
                        or got_guide_at is not null
                        or user_id in (select user_id from purchases
                                       where status in ('paid', 'delivered'))
                        order by user_id""", fetch="all") or []
        ok = 0
        for i in range(0, len(us), BATCH):
            ok += post({"users": [user_row(u) for u in us[i:i + BATCH]], "purchases": []})
        for i in range(0, len(ps), BATCH):
            ok += post({"users": [], "purchases": [purchase_row(p) for p in ps[i:i + BATCH]]})
        log.info("міст: звірка, людей %d, покупок %d, пачок прийнято %d", len(us), len(ps), ok)
        return ok
    except Exception as e:
        log.warning("міст: звірка впала: %s", e)
        return 0
    finally:
        _zvirka_lock.release()


def _loop():
    _sleep(START_DELAY_S)
    while True:
        zvirka()
        _sleep(ZVIRKA_S)


def start():
    """Потік звірки: на старті і раз на ZVIRKA_S. Без змінних нічого."""
    if not ON:
        return None
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
