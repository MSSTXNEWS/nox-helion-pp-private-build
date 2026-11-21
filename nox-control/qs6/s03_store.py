"""s03_store: единое хранилище памяти NOX (SQLite): факты, эпизоды, профиль, журнал изменений.

Уверенность фактов считает лестница Riverse (community/riverse_ladder.py) в ТОЙ ЖЕ базе
(таблицы facts/evidence/transitions у лестницы, наши таблицы с префиксом mem_).
Импорт старой памяти и личности из каталога распакованного бэкапа: форматы определяются
по содержимому (SQLite / JSON / JSONL / Markdown / текст), отчёт - что принято, что отброшено и почему.
"""
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "community"))
from riverse_ladder import Ladder, LEVELS, norm_text  # noqa: E402

FACT_KINDS = ("core", "owner", "setting", "fact")
PROFILE_SECTIONS = ("persona", "owner", "settings", "other")
OWNER_SOURCE_KIND = "owner"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mem_facts(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'fact', text TEXT NOT NULL, key TEXT,
  ladder_id INTEGER, status TEXT NOT NULL DEFAULT 'active', pinned INTEGER NOT NULL DEFAULT 0,
  owner_confirmed INTEGER NOT NULL DEFAULT 0, importance REAL NOT NULL DEFAULT 0.5,
  source TEXT, created REAL, updated REAL, last_access REAL, access_count INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS mem_facts_key ON mem_facts(key) WHERE status='active';
CREATE TABLE IF NOT EXISTS mem_episodes(
  id INTEGER PRIMARY KEY, ts REAL, role TEXT, text TEXT NOT NULL, summary TEXT, session TEXT,
  key TEXT, status TEXT NOT NULL DEFAULT 'active', source TEXT, owner_confirmed INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS mem_episodes_key ON mem_episodes(key) WHERE status='active';
CREATE TABLE IF NOT EXISTS mem_profile(
  key TEXT PRIMARY KEY, section TEXT NOT NULL DEFAULT 'other', value TEXT NOT NULL, source TEXT,
  status TEXT NOT NULL DEFAULT 'active', updated REAL);
CREATE TABLE IF NOT EXISTS mem_changes(
  id INTEGER PRIMARY KEY, ts REAL, actor TEXT, action TEXT, ref TEXT, old TEXT, new TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS mem_usage(
  id INTEGER PRIMARY KEY, turn_id TEXT, ref TEXT, ts REAL, score REAL, query TEXT, via TEXT);
CREATE INDEX IF NOT EXISTS mem_usage_turn ON mem_usage(turn_id);
CREATE TABLE IF NOT EXISTS mem_vectors(ref TEXT PRIMARY KEY, model TEXT, dim INTEGER, vec BLOB, text_key TEXT);
CREATE TABLE IF NOT EXISTS mem_import_reports(id INTEGER PRIMARY KEY, ts REAL, root TEXT, report TEXT);
"""

SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:password|passwd|пароль|token|токен|api[_-]?key|secret)\s*[:=]\s*\S{6,})",
    re.I)


def ref_of(kind, ident):
    return "%s:%s" % ({"fact": "f", "episode": "e", "profile": "p"}[kind], ident)


def split_ref(ref):
    p, _, i = str(ref).partition(":")
    kinds = {"f": "fact", "e": "episode", "p": "profile"}
    if p not in kinds or not i:
        raise ValueError("неверный id воспоминания: %r" % (ref,))
    return kinds[p], (i if p == "p" else int(i))


def parse_ts(v, default=None):
    """epoch (сек/мс) или ISO-строка -> epoch-секунды."""
    if v is None or v == "":
        return default
    if isinstance(v, (int, float)):
        v = float(v)
        return v / 1000.0 if v > 1e11 else v
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return parse_ts(float(s), default)
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:
        return default


class Store:
    def __init__(self, path=":memory:"):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = None
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.ladder = self._make_ladder()
        self.fts = self._init_fts()
        self.db.commit()

    # --- внутреннее ---
    def _make_ladder(self):
        """Лестница Riverse на нашем соединении (таблицы facts/evidence/transitions в той же базе)."""
        lad = Ladder(":memory:")
        ddl = [r[0] for r in lad.db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")]
        lad.db.close()
        for s in ddl:
            self.db.execute(s.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
        lad.db = self.db
        return lad

    def _init_fts(self):
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5("
                            "ref UNINDEXED, body, tokenize='unicode61 remove_diacritics 2')")
            return True
        except sqlite3.OperationalError:
            return False

    def close(self):
        self.db.close()

    def _log(self, actor, action, ref, old=None, new=None, reason=None, ts=None):
        cur = self.db.execute("INSERT INTO mem_changes(ts,actor,action,ref,old,new,reason) VALUES(?,?,?,?,?,?,?)",
                              (ts or time.time(), actor, action, ref, old, new, reason))
        return cur.lastrowid

    def _fts_set(self, ref, body):
        if not self.fts:
            return
        self.db.execute("DELETE FROM mem_fts WHERE ref=?", (ref,))
        if body is not None:
            self.db.execute("INSERT INTO mem_fts(ref, body) VALUES(?,?)", (ref, body))

    # --- факты ---
    def add_fact(self, text, kind="fact", source="owner", source_kind=None, pinned=False, importance=0.5,
                 ts=None, actor="system", log=True):
        """Добавить факт (дубликат по нормализованному тексту -> тот же id + новое свидетельство)."""
        text = (text or "").strip()
        if not text:
            raise ValueError("пустой факт")
        if kind not in FACT_KINDS:
            raise ValueError("kind: %s" % "|".join(FACT_KINDS))
        ts = ts or time.time()
        key = norm_text(text)
        row = self.db.execute("SELECT id, ladder_id FROM mem_facts WHERE key=? AND status='active'", (key,)).fetchone()
        sk = source_kind or (OWNER_SOURCE_KIND if source == "owner" else "chat")
        if row:
            self.lad_evidence(row[1], source or "?", sk, ts)
            self.db.commit()
            return row[0]
        lid = self.ladder.add_fact(text, ts)
        self.ladder.add_evidence(lid, source or "?", sk, ts)
        cur = self.db.execute(
            "INSERT INTO mem_facts(kind,text,key,ladder_id,pinned,importance,source,created,updated,last_access)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)", (kind, text, key, lid, int(bool(pinned)), importance, source, ts, ts, ts))
        fid = cur.lastrowid
        self._fts_set(ref_of("fact", fid), text)
        if log:
            self._log(actor, "add", ref_of("fact", fid), None, text, "kind=%s" % kind, ts)
        self.db.commit()
        return fid

    def lad_evidence(self, lid, source, kind, ts):
        return self.ladder.add_evidence(lid, source, kind, ts)

    def level_of(self, fact_row_id):
        """Эффективный уровень уверенности 0..3 (лестница; подтверждение владельца даёт минимум 2)."""
        r = self.db.execute("SELECT ladder_id, owner_confirmed FROM mem_facts WHERE id=?", (fact_row_id,)).fetchone()
        if not r:
            return 0
        lvl = self.ladder.level(r[0])
        return max(lvl, 2) if r[1] else lvl

    def get_fact(self, fid):
        r = self.db.execute("SELECT id,kind,text,status,pinned,owner_confirmed,importance,source,created,updated,"
                            "last_access,access_count,ladder_id FROM mem_facts WHERE id=?", (fid,)).fetchone()
        if not r:
            return None
        d = dict(zip(("id", "kind", "text", "status", "pinned", "owner_confirmed", "importance", "source",
                      "created", "updated", "last_access", "access_count", "ladder_id"), r))
        d["level"] = max(self.ladder.level(d["ladder_id"]), 2 if d["owner_confirmed"] else 0)
        d["level_name"] = LEVELS[d["level"]]
        d["ref"] = ref_of("fact", fid)
        return d

    def active_facts(self, kinds=None):
        q = "SELECT id FROM mem_facts WHERE status='active'"
        args = []
        if kinds:
            q += " AND kind IN (%s)" % ",".join("?" * len(kinds))
            args = list(kinds)
        return [self.get_fact(i) for (i,) in self.db.execute(q + " ORDER BY id", args)]

    def touch(self, ref, ts=None):
        """Обращение к воспоминанию (для свежести/использования)."""
        kind, i = split_ref(ref)
        if kind == "fact":
            self.db.execute("UPDATE mem_facts SET last_access=?, access_count=access_count+1 WHERE id=?",
                            (ts or time.time(), i))
            self.db.commit()

    # --- эпизоды ---
    def add_episode(self, text, role="user", ts=None, session=None, summary=None, source="chat", actor="system"):
        text = (text or "").strip()
        if not text:
            raise ValueError("пустой эпизод")
        ts = ts or time.time()
        key = norm_text("%s|%s|%s" % (role, int(ts), text))
        r = self.db.execute("SELECT id FROM mem_episodes WHERE key=? AND status='active'", (key,)).fetchone()
        if r:
            return r[0]
        cur = self.db.execute("INSERT INTO mem_episodes(ts,role,text,summary,session,key,source) VALUES(?,?,?,?,?,?,?)",
                              (ts, role, text, summary, session, key, source))
        eid = cur.lastrowid
        self._fts_set(ref_of("episode", eid), text + (" " + summary if summary else ""))
        self.db.commit()
        return eid

    def get_episode(self, eid):
        r = self.db.execute("SELECT id,ts,role,text,summary,session,status,source,owner_confirmed FROM mem_episodes "
                            "WHERE id=?", (eid,)).fetchone()
        if not r:
            return None
        d = dict(zip(("id", "ts", "role", "text", "summary", "session", "status", "source", "owner_confirmed"), r))
        d["ref"] = ref_of("episode", eid)
        return d

    # --- профиль ---
    def set_profile(self, key, value, section="other", source="owner", actor="system", ts=None):
        if section not in PROFILE_SECTIONS:
            raise ValueError("section: %s" % "|".join(PROFILE_SECTIONS))
        key, value = str(key).strip(), str(value).strip()
        if not key or not value:
            raise ValueError("пустой ключ/значение профиля")
        old = self.db.execute("SELECT value FROM mem_profile WHERE key=? AND status='active'", (key,)).fetchone()
        ts = ts or time.time()
        self.db.execute("INSERT INTO mem_profile(key,section,value,source,status,updated) VALUES(?,?,?,?, 'active',?) "
                        "ON CONFLICT(key) DO UPDATE SET section=excluded.section, value=excluded.value, "
                        "source=excluded.source, status='active', updated=excluded.updated",
                        (key, section, value, source, ts))
        ref = ref_of("profile", key)
        self._fts_set(ref, key + ": " + value)
        self._log(actor, "set" if old else "add", ref, old[0] if old else None, value, None, ts)
        self.db.commit()
        return ref

    def get_profile(self, key):
        r = self.db.execute("SELECT key,section,value,source,status,updated FROM mem_profile WHERE key=?", (key,)).fetchone()
        if not r:
            return None
        d = dict(zip(("key", "section", "value", "source", "status", "updated"), r))
        d["ref"] = ref_of("profile", key)
        return d

    def profile(self, section=None):
        q = "SELECT key,section,value,source,updated FROM mem_profile WHERE status='active'"
        args = []
        if section:
            q += " AND section=?"
            args.append(section)
        return [dict(zip(("key", "section", "value", "source", "updated"), r)) for r in self.db.execute(q + " ORDER BY key", args)]

    # --- универсальный доступ по id ---
    def get(self, ref):
        kind, i = split_ref(ref)
        d = {"fact": self.get_fact, "episode": self.get_episode, "profile": self.get_profile}[kind](i)
        if d is not None:
            d["type"] = kind
        return d

    def text_of(self, rec):
        if rec["type"] == "profile":
            return "%s: %s" % (rec["key"], rec["value"])
        return rec["text"]

    def stats(self):
        q = lambda s: self.db.execute(s).fetchone()[0]
        return {"facts": q("SELECT COUNT(*) FROM mem_facts WHERE status='active'"),
                "episodes": q("SELECT COUNT(*) FROM mem_episodes WHERE status='active'"),
                "profile": q("SELECT COUNT(*) FROM mem_profile WHERE status='active'"),
                "changes": q("SELECT COUNT(*) FROM mem_changes"), "fts5": self.fts}

    def reindex_fts(self):
        """Пересобрать полнотекстовый индекс (после восстановления/импорта в обход API)."""
        if not self.fts:
            return 0
        self.db.execute("DELETE FROM mem_fts")
        n = 0
        for i, t in self.db.execute("SELECT id,text FROM mem_facts WHERE status='active'").fetchall():
            self._fts_set(ref_of("fact", i), t); n += 1
        for i, t, s in self.db.execute("SELECT id,text,summary FROM mem_episodes WHERE status='active'").fetchall():
            self._fts_set(ref_of("episode", i), t + (" " + s if s else "")); n += 1
        for k, v in self.db.execute("SELECT key,value FROM mem_profile WHERE status='active'").fetchall():
            self._fts_set(ref_of("profile", k), k + ": " + v); n += 1
        self.db.commit()
        return n

    # --- импорт ---
    def import_dir(self, root, actor="import", dry_run=False):
        from .s03_import import import_tree
        return import_tree(self, root, actor=actor, dry_run=dry_run)
