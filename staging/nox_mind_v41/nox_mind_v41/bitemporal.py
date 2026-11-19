"""Bi-temporal fact store (Graphiti/Zep style). Each fact has 4 timestamps:
valid_at / invalid_at  - when the fact is true in the world (event time)
created_at / expired_at - when the system learned / retired the record (transaction time)
Nothing is silently deleted: a contradicting fact SUPERSEDES the old one (old.expired_at + old.invalid_at set,
supersession edge kept). Provenance (source, reasoning trace id) is stored per fact = context graph.
MEMOIR-style importance revision + UCB exploration for retrieval ranking."""
import sqlite3, time, hashlib, json, math

SCHEMA = """
CREATE TABLE IF NOT EXISTS fact(id TEXT PRIMARY KEY, persona_id TEXT, subject TEXT, predicate TEXT, object TEXT,
  valid_at REAL, invalid_at REAL, created_at REAL, expired_at REAL,
  source TEXT, trace_id TEXT, importance REAL DEFAULT 0.5, uses INTEGER DEFAULT 0, reward REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS supersession(old_id TEXT, new_id TEXT, at REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS trace(id TEXT PRIMARY KEY, at REAL, kind TEXT, payload TEXT);
CREATE INDEX IF NOT EXISTS fact_sp ON fact(persona_id, subject, predicate);
"""

class BiTemporalStore:
    def __init__(self, path=":memory:", clock=time.time):
        self.db = sqlite3.connect(path, check_same_thread=False); self.db.executescript(SCHEMA); self.clock = clock

    def trace(self, kind, payload):
        tid = hashlib.sha256(f"{kind}{self.clock()}{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()).hexdigest()[:16]
        self.db.execute("INSERT OR REPLACE INTO trace VALUES(?,?,?,?)", (tid, self.clock(), kind, json.dumps(payload, ensure_ascii=False)))
        return tid

    def assert_fact(self, persona_id, subject, predicate, obj, valid_at=None, source="chat", trace_id=None,
                    importance=0.5, functional=True, reason="contradiction"):
        """functional=True: (subject,predicate) has a single current value -> older current values are superseded."""
        now = self.clock(); valid_at = now if valid_at is None else valid_at
        fid = hashlib.sha256(f"{persona_id}|{subject}|{predicate}|{obj}|{valid_at}|{now}".encode()).hexdigest()[:16]
        cur = self.current(persona_id, subject, predicate)
        for c in cur:
            if c["object"] == obj:
                return c["id"]  # idempotent
        self.db.execute("INSERT INTO fact(id,persona_id,subject,predicate,object,valid_at,invalid_at,created_at,expired_at,source,trace_id,importance)"
                        " VALUES(?,?,?,?,?,?,NULL,?,NULL,?,?,?)", (fid, persona_id, subject, predicate, obj, valid_at, now, source, trace_id, importance))
        if functional:
            for c in cur:
                self.db.execute("UPDATE fact SET expired_at=?, invalid_at=COALESCE(invalid_at, ?) WHERE id=?", (now, valid_at, c["id"]))
                self.db.execute("INSERT INTO supersession VALUES(?,?,?,?)", (c["id"], fid, now, reason))
        self.db.commit(); return fid

    def _rows(self, sql, args):
        cols = ["id", "persona_id", "subject", "predicate", "object", "valid_at", "invalid_at", "created_at", "expired_at",
                "source", "trace_id", "importance", "uses", "reward"]
        return [dict(zip(cols, r)) for r in self.db.execute(sql, args)]

    def current(self, persona_id, subject, predicate):
        return self._rows("SELECT * FROM fact WHERE persona_id=? AND subject=? AND predicate=? AND expired_at IS NULL", (persona_id, subject, predicate))

    def as_of(self, persona_id, subject, predicate, world_t, known_t=None):
        """What was true at world time world_t, according to what the system knew at known_t (default now).
        Supersession: the old fact stays true for its [valid_at, invalid_at) window; its invalid_at is only
        'known' from expired_at on. Retraction (retire): the fact disappears for known_t >= expired_at."""
        known_t = self.clock() if known_t is None else known_t
        retracted = {r[0]: r[1] for r in self.db.execute("SELECT old_id, at FROM supersession WHERE new_id IS NULL")}
        out = []
        for r in self._rows("SELECT * FROM fact WHERE persona_id=? AND subject=? AND predicate=? AND created_at<=? AND valid_at<=?",
                            (persona_id, subject, predicate, known_t, world_t)):
            if r["id"] in retracted and retracted[r["id"]] <= known_t:
                continue
            inv_known = r["invalid_at"] is not None and r["expired_at"] is not None and r["expired_at"] <= known_t
            if inv_known and r["invalid_at"] <= world_t:
                continue
            out.append(r)
        return out

    def history(self, persona_id, subject, predicate):
        return self._rows("SELECT * FROM fact WHERE persona_id=? AND subject=? AND predicate=? ORDER BY created_at", (persona_id, subject, predicate))

    def retire(self, fact_id, reason="user_retracted"):
        """Soft retraction (no delete)."""
        self.db.execute("UPDATE fact SET expired_at=? WHERE id=? AND expired_at IS NULL", (self.clock(), fact_id))
        self.db.execute("INSERT INTO supersession VALUES(?,?,?,?)", (fact_id, None, self.clock(), reason)); self.db.commit()

    # ---- MEMOIR-style importance revision + UCB ----
    def feedback(self, fact_id, reward):
        self.db.execute("UPDATE fact SET uses=uses+1, reward=reward+?, importance=MIN(1.0, MAX(0.0, importance + 0.1*(?-0.5))) WHERE id=?",
                        (reward, reward, fact_id)); self.db.commit()

    def rank(self, persona_id, candidates_ids=None, c=0.5, k=5):
        rows = self._rows("SELECT * FROM fact WHERE persona_id=? AND expired_at IS NULL", (persona_id,))
        if candidates_ids is not None:
            rows = [r for r in rows if r["id"] in set(candidates_ids)]
        n = sum(r["uses"] for r in rows) + 1
        for r in rows:
            mean = (r["reward"] / r["uses"]) if r["uses"] else r["importance"]
            r["ucb"] = 0.5 * r["importance"] + 0.5 * mean + c * math.sqrt(math.log(n + 1) / (r["uses"] + 1))
        return sorted(rows, key=lambda r: -r["ucb"])[:k]
