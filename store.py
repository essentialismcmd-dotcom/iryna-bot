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

import os, json, time, logging, threading
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
    cabinet_msg   bigint,
    tasks_msg     bigint
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

create table if not exists tasks (
    id          bigserial primary key,
    owner       text not null,
    n           integer not null,
    text        text not null,
    done        boolean not null default false,
    project     text,
    deferred_at timestamptz,
    created_by  bigint,
    created_at  timestamptz not null default now(),
    closed_at   timestamptz,
    unique (owner, n)
);
alter table tasks add column if not exists project text;
alter table tasks add column if not exists deferred_at timestamptz;

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

create table if not exists blocks (
    id       bigserial primary key,
    kind     text not null default 'other',
    code     text,
    title    text not null,
    position integer not null default 0,
    active   boolean not null default true,
    unique (kind, code)
);
alter table assets add column if not exists block_id bigint;
alter table users add column if not exists active_block bigint;
alter table users add column if not exists block_msg bigint;
alter table users add column if not exists as_ira boolean not null default false;
create index if not exists assets_block on assets (block_id);
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
    allowed = ("source_tag", "got_magnet_at", "cabinet_msg", "tasks_msg", "role",
               "active_block", "block_msg", "as_ira")
    fields = {k: v for k, v in kw.items() if k in allowed}
    if not fields:
        return None
    sets = ", ".join(k + " = %s" for k in fields)
    return q("update users set " + sets + " where user_id = %s",
             tuple(fields.values()) + (uid,))


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
              media_group=None, file_unique_id=None, block_id=None):
    return q("""
        insert into assets (from_user, file_id, file_unique_id, file_kind, bucket,
                            caption, media_group, block_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s) returning *
    """, (from_user, file_id, file_unique_id, file_kind, bucket, caption,
          media_group, block_id), fetch="one")


def get_asset(asset_id):
    return q("select * from assets where id = %s", (asset_id,), fetch="one")


def set_bucket(asset_id, bucket):
    return q("update assets set bucket = %s where id = %s returning *",
             (bucket, asset_id), fetch="one")


def set_bucket_group(media_group, bucket):
    """Розкладає весь альбом одним рухом. Повертає скільки карток перекладено."""
    r = q("""update assets set bucket = %s where media_group = %s and bucket = 'inbox'
             returning id""", (bucket, media_group), fetch="all")
    return len(r or [])


def assets_of_group(media_group, limit=50):
    return q("""select * from assets where media_group = %s order by id limit %s""",
             (media_group, limit), fetch="all")


def inbox_count():
    r = q("select count(*) as n from assets where bucket = 'inbox'", fetch="one")
    return (r or {}).get("n", 0)


def inbox_next():
    """Найстарша нерозкладена картка. Альбом представлений своєю першою карткою."""
    return q("""select * from assets where bucket = 'inbox'
                order by created_at, id limit 1""", fetch="one")


def bucket_assets(bucket, limit=20, unused_only=False):
    sql = "select * from assets where bucket = %s"
    if unused_only:
        sql += " and used_at is null"
    sql += " order by created_at desc limit %s"
    return q(sql, (bucket, limit), fetch="all")


def mark_asset_used(asset_id):
    return q("update assets set used_at = now() where id = %s", (asset_id,))


def bucket_counts():
    return q("""select bucket, count(*) as n, count(used_at) as used
                from assets group by bucket order by n desc""", fetch="all")


# ---------- блоки матеріалів ----------
#
# Блок це не стан, а вказівник: куди зараз падає матеріал від Іри.
# Активний блок завжди один, решта просто містять матеріали, і назавжди.
# Тому закривати нічого не треба, протухає лише вказівник.

def seed_blocks(rows):
    """rows: список (kind, code, title, position). Наявні не чіпає."""
    n = 0
    for kind, code, title, pos in rows:
        r = q("""insert into blocks (kind, code, title, position) values (%s, %s, %s, %s)
                 on conflict (kind, code) do nothing returning id""",
              (kind, code, title, pos), fetch="one")
        if r:
            n += 1
    return n


def list_blocks(kind=None):
    if kind:
        return q("""select * from blocks where active and kind = %s
                    order by position, id""", (kind,), fetch="all")
    return q("select * from blocks where active order by kind, position, id", fetch="all")


def block_kinds():
    return q("""select kind, count(*) as n from blocks where active
                group by kind order by min(position)""", fetch="all")


def get_block(bid):
    return q("select * from blocks where id = %s", (bid,), fetch="one")


def inbox_block():
    """
    Блок за замовчуванням. Якщо вона нічого не обрала, матеріал падає сюди,
    а не в порожнечу. Нічого питати в неї для цього не треба.
    """
    r = q("""select * from blocks where kind = 'other' and code = '_inbox'""", fetch="one")
    if r:
        return r
    return q("""insert into blocks (kind, code, title, position, active)
                values ('other', '_inbox', 'Без блоку', 999, false)
                on conflict (kind, code) do update set title = excluded.title
                returning *""", fetch="one")


def find_block(text):
    """
    Пошук блоку за текстом на кшталт «Схема 5», «схема 05», «Обкладинка».
    Спершу точний номер, далі назва. Нічого не знайшли, повертаємо None,
    і повідомлення йде звичайним матеріалом.
    """
    t = (text or "").strip()
    if not t or len(t) > 60:
        return None
    import re as _re
    # Вона пише живою мовою: «Це все для схеми 8», «далі схема 8», «ось схема 8».
    # Тому не шукаємо точний шаблон, а прибираємо оголошення і дивимось,
    # чи лишився зміст. Лишився, значить це матеріал, а не заголовок.
    m = _re.search(r"схем\w*\s*[№#]?\s*0*(\d{1,2})", t, _re.I)
    if m:
        rest = (t[:m.start()] + " " + t[m.end():]).lower()
        rest = _re.sub(r"[^\w\s]", " ", rest, flags=_re.U)
        stop = {"це", "оце", "все", "всі", "усе", "для", "по", "до", "на", "далі",
                "тепер", "зараз", "і", "а", "ось", "от", "кидаю", "скидаю", "надсилаю",
                "буде", "будуть", "наступна", "наступне", "ще", "тут", "щодо", "така",
                "нова", "оновлена", "переробила", "мій", "моя"}
        if not [w for w in rest.split() if w not in stop]:
            return q("select * from blocks where active and code = %s and kind = 'schema'",
                     (m.group(1),), fetch="one")
        return None
    if len(t) > 30:
        return None
    return q("""select * from blocks where active and lower(title) = lower(%s)
                order by position limit 1""", (t.strip(".").strip(),), fetch="one")


def set_active_block(uid, bid):
    return q("update users set active_block = %s where user_id = %s", (bid, uid))


def active_block(uid):
    r = q("""select b.* from users u join blocks b on b.id = u.active_block
             where u.user_id = %s""", (uid,), fetch="one")
    return r


def block_tally(bid):
    """Скільки і чого лежить у блоці, для лічильника в картці."""
    return q("""select coalesce(file_kind, 'матеріал') as kind, count(*) as n
                from assets where block_id = %s group by 1 order by n desc""",
             (bid,), fetch="all")


def blocks_with_material():
    return q("""select b.id, b.kind, b.code, b.title, count(a.id) as n,
                       max(a.created_at) as last_at
                from blocks b join assets a on a.block_id = b.id
                group by b.id, b.kind, b.code, b.title
                order by max(a.created_at) desc""", fetch="all")


# ---------- задачник ----------

def tasks_of(owner, only_open=False, project=None):
    sql = "select * from tasks where owner = %s"
    args = [owner]
    if only_open:
        sql += " and not done"
    if project:
        sql += " and coalesce(project, '') = %s"
        args.append(project)
    sql += " order by n"
    return q(sql, tuple(args), fetch="all")


def add_task(owner, text, created_by=None, project=None):
    return q("""
        insert into tasks (owner, n, text, created_by, project)
        values (%s, coalesce((select max(n) from tasks where owner = %s), 0) + 1, %s, %s, %s)
        returning *
    """, (owner, owner, text, created_by, project), fetch="one")


def close_task(owner, n):
    return q("""update tasks set done = true, closed_at = now()
                where owner = %s and n = %s and not done returning *""", (owner, n), fetch="one")


def delete_task(owner, n):
    return q("delete from tasks where owner = %s and n = %s returning *", (owner, n), fetch="one")


def set_task_project(owner, n, project):
    return q("""update tasks set project = %s where owner = %s and n = %s returning *""",
             (project or None, owner, n), fetch="one")


def defer_task(owner, n):
    """Відкладає задачу в кінець черги «що зараз», не закриваючи її."""
    return q("""update tasks set deferred_at = now()
                where owner = %s and n = %s and not done returning *""", (owner, n), fetch="one")


def next_task(owner, project=None):
    """
    Рівно одна задача на питання «що зараз»: найстарша відкрита,
    відкладені йдуть після невідкладених.
    """
    sql = "select * from tasks where owner = %s and not done"
    args = [owner]
    if project:
        sql += " and coalesce(project, '') = %s"
        args.append(project)
    sql += " order by deferred_at nulls first, n limit 1"
    return q(sql, tuple(args), fetch="one")


def projects_of(owner):
    return q("""select coalesce(project, '') as project, count(*) as n
                from tasks where owner = %s and not done
                group by 1 order by n desc""", (owner,), fetch="all")


def seed_tasks(owner, items):
    """Засіває список один раз. Якщо в цього власника вже щось є, нічого не робить."""
    if tasks_of(owner):
        return 0
    for t in items:
        add_task(owner, t)
    return len(items)


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


# ---------- вивантаження ----------

TABLES = ("users", "purchases", "assets", "tasks", "events", "mono_tx", "kv")


def export_all():
    out = {}
    for t in TABLES:
        out[t] = q("select * from " + t + " order by 1", fetch="all") or []
    return json.dumps(out, ensure_ascii=False, indent=1, default=str).encode("utf-8")


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
