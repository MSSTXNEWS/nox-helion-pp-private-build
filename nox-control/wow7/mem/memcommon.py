"""memcommon: общие мелочи модулей MEM (без зависимостей): нормализация, дни по МСК, стемы, схема таблиц mem_*.

Модули MEM работают поверх ТОЙ ЖЕ SQLite, что и qs6/s03_store.Store (store.db, store.path, store.fts,
store.get/get_fact/active_facts/_log/_fts_set, store.ladder). Свои таблицы создаются через CREATE IF NOT EXISTS
и не трогают существующие.
"""
import re
import sqlite3
import threading
import time

DAY = 86400.0
MSK = 3 * 3600  # владелец живёт по Москве; сутки автобиографии считаются по МСК

STOP = frozenset("""это что как так для при или если уже ещё еще его ее её они она оно тот тут там где когда
чтобы потому только очень можно нужно надо будет быть есть был была были него неё них нам вас мне мой моя
мои наш наша свой своя про над под без между после перед через также который которая которые эти этот эта
все всё всего всех вот ну да нет не ни же бы ли мессир""".split())

SCHEMA = """
CREATE TABLE IF NOT EXISTS mem_revoked(
  key TEXT PRIMARY KEY, ref TEXT, ts REAL, actor TEXT, reason TEXT, change_id INTEGER, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS mem_corrections(
  id INTEGER PRIMARY KEY, ts REAL, ref TEXT, op TEXT, old TEXT, new TEXT, verified INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS mem_usage_snap(
  turn_id TEXT, ref TEXT, via TEXT, text TEXT, text_sha TEXT, level INTEGER, source TEXT, ts REAL,
  PRIMARY KEY(turn_id, ref));
CREATE TABLE IF NOT EXISTS mem_consolidated(episode_id INTEGER PRIMARY KEY, ts REAL);
CREATE TABLE IF NOT EXISTS mem_questions(
  id INTEGER PRIMARY KEY, ts REAL, kind TEXT, a_ref TEXT, b_ref TEXT, pair TEXT UNIQUE, question TEXT,
  status TEXT NOT NULL DEFAULT 'open', answer TEXT, answered_ts REAL);
CREATE TABLE IF NOT EXISTS mem_autobio(day TEXT PRIMARY KEY, text TEXT, data TEXT, ts REAL);
"""


BUSY_MS = 10000
_W = threading.RLock()      # писатель S03 внутри процесса один: коммиты MEM идут через commit() под этим замком


def harden(store):
    """WAL + busy_timeout на соединении (REVIEW_1 п.4.2): параллельные писатели (gateway, MEM-06, CTX, CON) ждут, а не падают.
    Межпроцессно запись сериализует SQLite (WAL: один писатель), внутри процесса - замок _W + повтор при 'database is locked'."""
    try:
        if getattr(store, "path", ":memory:") not in (":memory:", "", None):
            store.db.execute("PRAGMA journal_mode=WAL")
        store.db.execute("PRAGMA busy_timeout=%d" % BUSY_MS)
    except sqlite3.Error:
        pass


def commit(store, retries=20):
    """Единая точка коммита MEM: замок писателя + повтор при блокировке (экспоненциально до ~BUSY_MS*retries)."""
    with _W:
        for i in range(retries):
            try:
                store.db.commit()
                return
            except sqlite3.OperationalError as e:
                if ("locked" not in str(e) and "busy" not in str(e)) or i == retries - 1:
                    raise
                time.sleep(min(2.0, 0.1 * (i + 1)))


def ensure_schema(store):
    harden(store)
    store.db.executescript(SCHEMA)
    commit(store)


def norm_text(t):
    """Как riverse_ladder.norm_text: ключ дедупликации факта."""
    return re.sub(r"\s+", " ", t).strip().strip(".!?").casefold()


def day_of(ts, tz=MSK):
    return time.strftime("%Y-%m-%d", time.gmtime(float(ts) + tz))


def day_bounds(day, tz=MSK):
    """-> (start_ts, end_ts) в epoch UTC для суток 'YYYY-MM-DD' по часовому поясу tz."""
    t = time.strptime(day, "%Y-%m-%d")
    import calendar
    start = calendar.timegm(t) - tz
    return float(start), float(start + DAY)


def stems(text, n=5, min_len=4):
    """Основы слов (префикс n символов), без стоп-слов и чисел."""
    out = []
    for w in re.findall(r"[^\W\d_]+", (text or "").casefold()):
        if len(w) >= min_len and w not in STOP:
            out.append(w[:n])
    return out


def fresh_connection(store):
    """Новое соединение к файлу базы (видит только закоммиченное). Для :memory: - само соединение хранилища."""
    if getattr(store, "path", ":memory:") in (":memory:", "", None):
        return store.db, False
    return sqlite3.connect(store.path), True
