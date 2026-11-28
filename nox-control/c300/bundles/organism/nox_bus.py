#!/usr/bin/env python3
"""NOX шина событий (канон гл. 2): используется ЕЖЕ СУЩЕСТВУЮЩАЯ SQLite WAL state/bus/events.db (таблицы events(seq,id,ts,iso,source,kind,payload,trace_id) и board(k,v,ts)); Redis не ставим (его нет, канон: «Redis, если нужен»).
Добавляет журнал задач: task.started / task.progress / task.done / task.failed (+ task.queued, task.deferred, task.refused). Короткие транзакции, busy_timeout 5 с. stdlib."""
import os, sys, json, time, uuid, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C
SCHEMA = ["CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, ts REAL, iso TEXT, source TEXT, kind TEXT, payload TEXT, trace_id TEXT)",
          "CREATE TABLE IF NOT EXISTS board (k TEXT PRIMARY KEY, v TEXT, ts REAL)"]
def db_path(r=None): return (r or C.root()) + "/state/bus/events.db"
def conn(r=None, ro=False):
    p = db_path(r)
    if ro: return sqlite3.connect("file:%s?mode=ro" % p, uri=True, timeout=5)
    os.makedirs(os.path.dirname(p), exist_ok=True); cn = sqlite3.connect(p, timeout=5); cn.execute("PRAGMA busy_timeout=5000")
    if cn.execute("PRAGMA journal_mode").fetchone()[0] != "wal": cn.execute("PRAGMA journal_mode=WAL")
    return cn
def ensure(r=None):
    cn = conn(r)
    for s in SCHEMA:
        try: cn.execute(s)
        except sqlite3.OperationalError: pass   # индекс на большой боевой базе создаём без паники
    cn.commit(); cn.close()
def publish(kind, source, payload, trace_id=None, r=None, t=None):
    """-> seq события."""
    t = t if t is not None else time.time(); cn = conn(r)
    try:
        cur = cn.execute("INSERT INTO events(id,ts,iso,source,kind,payload,trace_id) VALUES(?,?,?,?,?,?,?)", ("ev_" + uuid.uuid4().hex[:16], t, time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)), source, kind, json.dumps(payload, ensure_ascii=False)[:2000], trace_id))
        cn.commit(); return cur.lastrowid
    finally: cn.close()
def recent(prefix="task.", n=50, r=None, trace_id=None):
    cn = conn(r, ro=True)
    try:
        q = "SELECT seq,ts,source,kind,payload,trace_id FROM events WHERE seq > (SELECT COALESCE(MAX(seq),0)-100000 FROM events) AND kind LIKE ?" + (" AND trace_id=?" if trace_id else "") + " ORDER BY seq DESC LIMIT ?"
        a = [prefix + "%"] + ([trace_id] if trace_id else []) + [n]
        return [dict(seq=x[0], ts=x[1], source=x[2], kind=x[3], payload=json.loads(x[4] or "{}"), trace_id=x[5]) for x in cn.execute(q, a)]
    except sqlite3.OperationalError: return []
    finally: cn.close()
def board_get(k, r=None):
    try:
        cn = conn(r, ro=True); row = cn.execute("SELECT v,ts FROM board WHERE k=?", (k,)).fetchone(); cn.close()
        if not row: return None
        try: v = json.loads(row[0])
        except Exception: v = {"text": row[0]}
        return dict(v, _ts=row[1]) if isinstance(v, dict) else {"text": str(v), "_ts": row[1]}
    except Exception: return None
