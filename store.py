#!/usr/bin/env python3
"""
Сховище бота: Postgres (Neon).

Правило номер один: зʼєднання відкривається на операцію і одразу закривається.
Neon не засинає, поки висить відкритий конекшен, а на безкоштовному плані
є тільки 100 CU-годин на місяць. Пул із постійними зʼєднаннями зʼїв би їх
приблизно за два тижні.

Правило номер два: без DATABASE_URL модуль мовчки вимикається і повертає
порожнечу. Бот від цього не падає, просто працює як раніше, без памʼяті.
"""

import os, time, logging, threading
from contextlib import contextmanager

log = logging.getLogger("store")

DSN = os.getenv("DATABASE_URL", "").strip()
ON = bool(DSN)

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    ON = False
    log.warning("psycopg не встановлений, сховище вимкнене")

_ready = False
_lock = threading.Lock()

SCHEMA = """
create table if not exists users (
    user_id       bigint primary key,
    username      text,
    first_name    text,
    last_name     text,
    role          text not null default 'client',
    source_tag    text,
    created_at    timestamptz not null default now(),
    last_seen_at  timestamptz not null default now(),
    got_magnet_at timestamptz,
    cabinet_msg   bigint
);

create table if not exists purchases (
    id           bigserial primary key,
    user_id      bigint not null,
    product      text not null,
    tier         text,
    order_code   text unique,
    amount_uah   integer,
    status       text not null default 'new',
    source_tag   text,
    slots_total  integer not null default 0,
    slots_used   integer not null default 0,
    created_at   timestamptz not null default now(),
    paid_at      timestamptz,
    delivered_at timestamptz
);
create index if not exists purchases_user on purchases (user_id);

create table if not exists assets (
    id             bigserial primary key,
    from_user      bigint,
    file_id        text not null,
    file_unique_id text,
    file_kind      text,
    bucket         text not null default 'inbox',
    caption        text,
    media_group    text,
    created_at     timestamptz not null default now(),
    used_at        timestamptz
);
alter table assets add column if not exists file_unique_id text;
create index if not exists assets_bucket on assets (bucket, created_at desc);
create index if not exists assets_group on assets (media_group);

create table if not exists events (
    id         bigserial primary key,
    user_id    bigint,
    kind       text not null,
    payload    jsonb,
    created_at timestamptz not null default now()
);
create index if not exists events_kind on events (kind, created_at desc);

create table if not exists mono_tx (
    tx_id        text primary key,
    amount       bigint,
    comment      text,
    handled_at   timestamptz not null default now()
);

create table if not exists kv (
    k          text primary key,
    v          text,
    updated_at timestamptz not null default now()
);

-- Дірект Instagram. Заведено 31.08.2026. Приймається вебхуком від офіційного
-- посередника Meta, бо прямого доступу до діректу немає: у токені відсутній
-- instagram_manage_messages, а Advanced Access упирається в верифікацію бізнесу.
-- Стан НЕ зберігається полем, він обчислюється з подій. Причина в handoff:
-- ручне поле «статус» стояло в значенні «нове» у 16 блоках з 18.
create table if not exists dm_contacts (
    id           bigserial primary key,
    ig_id        text unique not null,
    username     text,
    display_name text,
    segment      text,
    is_supplier  boolean not null default false,
    lang         text,
    first_seen   timestamptz,
    last_seen    timestamptz,
    created_at   timestamptz not null default now()
);
create index if not exists dm_contacts_seen on dm_contacts (last_seen desc);

create table if not exists dm_events (
    id         bigserial primary key,
    contact_id bigint not null references dm_contacts(id),
    ts         timestamptz not null,
    direction  text not null,
    kind       text not null default 'message',
    body       text,
    payload    jsonb,
    source     text not null default 'webhook',
    ext_id     text,
    unique (contact_id, ts, direction, kind, ext_id)
);
create index if not exists dm_events_contact on dm_events (contact_id, ts desc);
create index if not exists dm_events_ts on dm_events (ts desc);

-- Хто закрив угоду. Єдине поле, яке не залежить від жодного доступу до діректу,
-- і водночас єдине, що відповідає на головне питання проєкту: скільки закрилось
-- само, а скільки закрила людина руками.
create table if not exists dm_outcomes (
    id         bigserial primary key,
    contact_id bigint not null references dm_contacts(id),
    outcome    text not null,
    closed_by  text not null,
    amount     numeric,
    currency   text,
    ts         timestamptz not null default now(),
    note       text
);

create table if not exists dm_override (
    contact_id bigint primary key references dm_contacts(id),
    stage      text not null,
    reason     text not null,
    set_at     timestamptz not null default now()
);
-- 14.09.2026: файли курсу від адміна. Імʼя і розмір, щоб зібрати курс без
-- перегляду кожного відео.
alter table assets add column if not exists file_name text;
alter table assets add column if not exists file_size bigint;
"""


_local = threading.local()


# Жоден запит не має права висіти вічно. 28.08 бот повністю завис: зміна
# схеми при старті чекала блокування без обмеження часу, тримала загальний
# замок, і всі потоки gunicorn стали в чергу назавжди. Сервіс перестав
# віддавати навіть головну сторінку.
#
# Але через пулер їх передавати не можна: PgBouncer відкидає зʼєднання ще на
# рукостисканні з «unsupported startup parameter in options: statement_timeout».
# 28.08 я цим повністю поклав бота, вважаючи, що лагоджу зависання.
# Тому на пулері покладаємось на connect_timeout і запобіжник нижче.
PG_OPTS = ("-c statement_timeout=15000 -c lock_timeout=5000 "
           "-c idle_in_transaction_session_timeout=15000")
USE_OPTS = bool(DSN) and "-pooler" not in DSN


_down_until = 0.0    # база лежить, не чіпаємо її до цього моменту


def _open():
    """
    Дві спроби по пʼять секунд, не три по десять. Якщо база лягла, запит має
    померти швидко: 28.08 кожне звернення висіло 40 секунд, чотири таких
    зайняли всі потоки, і бот помер цілком через недоступну базу.
    """
    global _down_until
    err = None
    for attempt in range(2):
        try:
            kw = {"options": PG_OPTS} if USE_OPTS else {}
            c = psycopg.connect(DSN, connect_timeout=8, autocommit=True,
                                row_factory=dict_row, **kw)
            _down_until = 0.0
            return c
        except Exception as e:
            err = e
            if attempt == 0:
                time.sleep(0.5)
    _down_until = time.time() + 60
    log.warning("база недоступна, не чіпаю її хвилину: %s", err)
    raise err


def session_begin():
    """
    Одне зʼєднання на весь запит замість одного на операцію.
    Обробка повідомлення робить пʼять-шість звернень до бази, і на сплячому
    Neon кожне з них чекало пробудження окремо. Між запитами зʼєднання не
    лишається відкритим, тому база й далі засинає, як і задумано.
    """
    _local.conn = None
    _local.depth = getattr(_local, "depth", 0) + 1


def session_end():
    c = getattr(_local, "conn", None)
    _local.conn = None
    _local.depth = 0
    if c is not None:
        try:
            c.close()
        except Exception:
            pass


@contextmanager
def _conn():
    if getattr(_local, "depth", 0):
        if getattr(_local, "conn", None) is None:
            _local.conn = _open()
        yield _local.conn
        return
    c = _open()
    try:
        yield c
    finally:
        try:
            c.close()
        except Exception:
            pass


_schema_retry_at = 0.0


def _ensure():
    """
    Схема ставиться один раз на процес. Якщо не вийшло, наступна спроба не
    раніше ніж через хвилину: інакше кожен запит знову впирався б у неї і
    сервіс стояв би на місці.
    """
    global _ready, ON, _schema_retry_at
    if not ON:
        return False
    if time.time() < _down_until:
        return False          # база лежить, не витрачаємо на неї потік
    if _ready:
        return True
    if time.time() < _schema_retry_at:
        return False
    with _lock:
        if _ready:
            return True
        try:
            with _conn() as c:
                c.execute(SCHEMA)
            _ready = True
        except Exception as e:
            _schema_retry_at = time.time() + 60
            log.warning("схема не створилась, наступна спроба через хвилину: %s", e)
            return False
    return True


def q(sql, args=(), fetch=None):
    """fetch: None нічого не повертає, 'one' один рядок, 'all' список."""
    if not _ensure():
        return None if fetch != "all" else []
    try:
        with _conn() as c:
            cur = c.execute(sql, args)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return None
    except Exception as e:
        log.warning("запит впав: %s | %s", e, sql.strip().split("\n")[0])
        # Побите зʼєднання не тягнемо в наступні операції того самого запиту.
        c = getattr(_local, "conn", None)
        if c is not None:
            _local.conn = None
            try:
                c.close()
            except Exception:
                pass
        return None if fetch != "all" else []


# ---------- користувачі ----------

def touch_user(u, role="client", source_tag=None):
    """Записує або оновлює користувача. Мітка джерела пишеться тільки перший раз."""
    return q("""
        insert into users (user_id, username, first_name, last_name, role, source_tag)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (user_id) do update set
            username     = excluded.username,
            first_name   = excluded.first_name,
            last_name    = excluded.last_name,
            role         = excluded.role,
            source_tag   = coalesce(users.source_tag, excluded.source_tag),
            last_seen_at = now()
        returning *, (xmax = 0) as is_new
    """, (u.get("id"), u.get("username"), u.get("first_name"),
          u.get("last_name"), role, source_tag or None), fetch="one")


def get_user(uid):
    return q("select * from users where user_id = %s", (uid,), fetch="one")


def list_users(role=None):
    if role:
        return q("select * from users where role = %s order by created_at", (role,), fetch="all")
    return q("select * from users order by created_at", fetch="all")


def set_user(uid, **kw):
    allowed = ("source_tag", "got_magnet_at", "role")
    fields = {k: v for k, v in kw.items() if k in allowed}
    if not fields:
        return None
    sets = ", ".join(k + " = %s" for k in fields)
    return q("update users set " + sets + " where user_id = %s",
             tuple(fields.values()) + (uid,))


def wipe_user(uid):
    """
    Чистий лист для однієї людини: /skyd і /nova. Стирає її рядок users
    (мітка джерела, магніт), усі її заявки й покупки, включно з тестовими
    і ручними видачами, і журнал подій. Одним запитом, щоб не лишилось
    половини. Повертає лічильники або None, якщо база не відповіла.
    Матеріали (assets) не чіпає: там заливки файлів гайда від адміна.
    """
    return q("""
        with e as (delete from events where user_id = %s returning 1),
             p as (delete from purchases where user_id = %s returning 1),
             u as (delete from users where user_id = %s returning 1)
        select (select count(*) from u) as users,
               (select count(*) from p) as purchases,
               (select count(*) from e) as events
    """, (uid, uid, uid), fetch="one")


def mark_magnet(uid):
    return q("update users set got_magnet_at = coalesce(got_magnet_at, now()) where user_id = %s", (uid,))


# ---------- журнал подій ----------

def log_event(uid, kind, payload=None):
    """Дешева страховка: те, чого не записали сьогодні, заднім числом не зʼявиться."""
    if not ON:
        return None
    return q("insert into events (user_id, kind, payload) values (%s, %s, %s)",
             (uid, kind, Jsonb(payload) if payload is not None else None))


# ---------- покупки ----------

SLOTS = {"t1": 0, "t2": 1, "t3": 3}


def add_purchase(uid, product, tier=None, order_code=None, amount_uah=None, source_tag=None):
    return q("""
        insert into purchases (user_id, product, tier, order_code, amount_uah, source_tag, slots_total)
        values (%s, %s, %s, %s, %s,
                coalesce(%s, (select source_tag from users where user_id = %s)), %s)
        on conflict (order_code) do update set
            amount_uah = excluded.amount_uah
        returning *
    """, (uid, product, tier, order_code, amount_uah,
          source_tag, uid, SLOTS.get(tier, 0)), fetch="one")


def get_purchase(order_code):
    return q("select * from purchases where order_code = %s", (order_code,), fetch="one")


def purchases_of(uid, only_paid=True):
    sql = "select * from purchases where user_id = %s"
    if only_paid:
        sql += " and status in ('paid', 'delivered')"
    sql += " order by created_at"
    return q(sql, (uid,), fetch="all")


def mark_paid(order_code, amount_uah=None):
    return q("""
        update purchases set status = 'paid', paid_at = now(),
               amount_uah = coalesce(%s, amount_uah)
        where order_code = %s and status = 'new'
        returning *
    """, (amount_uah, order_code), fetch="one")


def mark_delivered(order_code):
    return q("""update purchases set status = 'delivered', delivered_at = now()
                where order_code = %s returning *""", (order_code,), fetch="one")


def use_slot(purchase_id):
    """Списує один розбір кадру. Повертає рядок, якщо слот був вільний."""
    return q("""
        update purchases set slots_used = slots_used + 1
        where id = %s and slots_used < slots_total
        returning *
    """, (purchase_id,), fetch="one")


# ---------- склад матеріалів ----------

def add_asset(from_user, file_id, file_kind, bucket="inbox", caption=None,
              media_group=None, file_unique_id=None,
              file_name=None, file_size=None):
    return q("""
        insert into assets (from_user, file_id, file_unique_id, file_kind, bucket,
                            caption, media_group, file_name, file_size)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *
    """, (from_user, file_id, file_unique_id, file_kind, bucket, caption,
          media_group, file_name, file_size), fetch="one")


def events_recent(limit=200):
    return q("select * from events order by created_at desc, id desc limit %s",
             (limit,), fetch="all")


def assets_recent(limit=200):
    """Усі матеріали, найновіші першими, будь-який кошик."""
    return q("select * from assets order by created_at desc, id desc limit %s",
             (limit,), fetch="all")


def get_asset(asset_id):
    return q("select * from assets where id = %s", (asset_id,), fetch="one")


def inbox_count():
    r = q("select count(*) as n from assets where bucket = 'inbox'", fetch="one")
    return (r or {}).get("n", 0)


# ---------- платежі Monobank ----------

def claim_tx(tx_id, amount, comment):
    """
    Позначає транзакцію обробленою. True тільки тому, хто взяв її першим.
    Захищає від двох речей: повторної видачі при рестарті і при кількох воркерах.
    """
    if not _ensure():
        return True
    r = q("""insert into mono_tx (tx_id, amount, comment) values (%s, %s, %s)
             on conflict (tx_id) do nothing returning tx_id""",
          (tx_id, amount, comment), fetch="one")
    return bool(r)


# ---------- дрібний стан ----------

def kv_get(k, default=None):
    r = q("select v from kv where k = %s", (k,), fetch="one")
    return r["v"] if r else default


def kv_set(k, v):
    return q("""insert into kv (k, v) values (%s, %s)
                on conflict (k) do update set v = excluded.v, updated_at = now()""", (k, str(v)))


def stats_day():
    """Цифри за добу, для рядка стану."""
    return {
        "starts": q("""select count(*) as n from users
                       where created_at > now() - interval '24 hours'""", fetch="one"),
        "magnet": q("""select count(*) as n from users
                       where got_magnet_at > now() - interval '24 hours'""", fetch="one"),
        "paid": q("""select count(*) as n, coalesce(sum(amount_uah), 0) as uah
                     from purchases where paid_at > now() - interval '24 hours'""", fetch="one"),
        "now": q("select now() as t", fetch="one"),
    }


def stats():
    return {
        "users": q("select count(*) as n from users", fetch="one"),
        "magnet": q("select count(*) as n from users where got_magnet_at is not null", fetch="one"),
        "by_tag": q("""select coalesce(source_tag, 'без мітки') as tag, count(*) as n
                       from users group by 1 order by n desc""", fetch="all"),
        "paid": q("""select count(*) as n, coalesce(sum(amount_uah), 0) as uah
                     from purchases where status in ('paid','delivered')""", fetch="one"),
    }


# ---------------------------------------------------------------- дірект
# Заведено 31.08.2026. Стан контакту НІКОЛИ не зберігається полем, він
# обчислюється з подій. Ручне поле «статус» у цьому проєкті вже вмирало:
# стояло в значенні «нове» у 16 блоках з 18, хоча на них давно відповіли.

def dm_contact(ig_id, username=None, display_name=None, lang=None, ts=None):
    """Знаходить або заводить контакт. Повертає id."""
    row = q("select id from dm_contacts where ig_id=%s", (str(ig_id),), fetch="one")
    if row:
        q("""update dm_contacts set username=coalesce(%s, username),
             display_name=coalesce(%s, display_name), lang=coalesce(%s, lang),
             last_seen=greatest(coalesce(last_seen, to_timestamp(0)), coalesce(%s, now()))
             where id=%s""", (username, display_name, lang, ts, row["id"]))
        return row["id"]
    row = q("""insert into dm_contacts (ig_id, username, display_name, lang, first_seen, last_seen)
               values (%s,%s,%s,%s, coalesce(%s, now()), coalesce(%s, now()))
               on conflict (ig_id) do update set username=excluded.username
               returning id""",
            (str(ig_id), username, display_name, lang, ts, ts), fetch="one")
    return row["id"] if row else None


def dm_event(contact_id, direction, body=None, ts=None, kind="message",
             payload=None, ext_id=None, source="webhook"):
    """direction: in (від людини) або out (від акаунта). Повтор безпечний."""
    if not contact_id:
        return
    q("""insert into dm_events (contact_id, ts, direction, kind, body, payload, source, ext_id)
         values (%s, coalesce(%s, now()), %s, %s, %s, %s, %s, %s)
         on conflict do nothing""",
      (contact_id, ts, direction, kind, body,
       Jsonb(payload) if (payload and psycopg) else None, source, ext_id))
    q("""update dm_contacts
         set last_seen = greatest(coalesce(last_seen, to_timestamp(0)), coalesce(%s, now()))
         where id=%s""", (ts, contact_id))


# Один запит, який відповідає на питання «що зараз у діректі».
# Усе тут похідне від подій, жодного збереженого статусу.
_DM_STATE = """
with ost as (
    select distinct on (contact_id) contact_id, ts, direction, body
      from dm_events order by contact_id, ts desc
),
lich as (
    select contact_id,
           count(*) filter (where direction='in')  as vid_ludyny,
           count(*) filter (where direction='out') as vid_nas,
           min(ts) as pershyi, max(ts) as ostannii
      from dm_events group by contact_id
)
select c.id, c.ig_id, c.username, c.display_name, c.segment, c.is_supplier, c.lang,
       l.vid_ludyny, l.vid_nas, l.pershyi, l.ostannii,
       o.direction as hto_ostannim, o.body as ostannie,
       extract(epoch from (now() - l.ostannii))/3600 as hodyn_movchannia,
       (o.direction='in' and o.body like '%%?%%') as pytannia_bez_vidpovidi,
       ov.stage as ruchnyi_etap,
       (select outcome from dm_outcomes where contact_id=c.id order by ts desc limit 1) as rezultat,
       (select closed_by from dm_outcomes where contact_id=c.id order by ts desc limit 1) as zakryv
  from dm_contacts c
  join lich l on l.contact_id=c.id
  left join ost o on o.contact_id=c.id
  left join dm_override ov on ov.contact_id=c.id
 where (%s or c.is_supplier=false)
 order by l.ostannii desc
 limit %s
"""


def dm_state(limit=50, include_suppliers=False):
    return q(_DM_STATE, (include_suppliers, limit), fetch="all") or []


def dm_one(kogo):
    """Пошук людини за username, ig_id або частиною імені."""
    return q("""select id, ig_id, username, display_name, segment, lang
                  from dm_contacts
                 where ig_id=%s or lower(username)=lower(%s)
                    or lower(display_name) like lower(%s)
                 order by last_seen desc limit 1""",
             (str(kogo), str(kogo), "%" + str(kogo) + "%"), fetch="one")


def dm_thread(contact_id, limit=40):
    return q("""select ts, direction, kind, body from dm_events
                 where contact_id=%s order by ts desc limit %s""",
             (contact_id, limit), fetch="all") or []


def dm_outcome(contact_id, outcome, closed_by, amount=None, currency=None, note=None):
    """closed_by: system | yaro | iryna. Без нього реєстр збреше про прибутковість."""
    q("""insert into dm_outcomes (contact_id, outcome, closed_by, amount, currency, note)
         values (%s,%s,%s,%s,%s,%s)""",
      (contact_id, outcome, closed_by, amount, currency, note))


def dm_stats():
    return {
        "kontaktiv": q("select count(*) as n from dm_contacts", fetch="one"),
        "podii": q("select count(*) as n from dm_events", fetch="one"),
        "svizhist": q("select max(ts) as ostannia from dm_events", fetch="one"),
        "zakryttia": q("""select closed_by, count(*) as n from dm_outcomes
                          where outcome='booked' group by 1""", fetch="all"),
    }


def asset_by_file_id(file_id):
    """Останній запис assets з цим file_id: з нього видно назву файлу (версію)."""
    return q("select * from assets where file_id = %s order by id desc limit 1",
             (file_id,), fetch="one")
