"""Graph personal memory: nodes typed by memory system (episodic/semantic/procedural/working) and edges by
dimension (semantic/temporal/relational/experiential/affective). Emotion-attended retrieval, dual-process
(online writer + offline abstraction) and a checkpoint store for long tasks. SQLite, stdlib only."""
import sqlite3, json, time, hashlib, re, math
from collections import Counter

MEM_TYPES = ("episodic", "semantic", "procedural", "working")
DIMENSIONS = ("semantic", "temporal", "relational", "experiential", "affective")

SCHEMA = """
CREATE TABLE IF NOT EXISTS node(id TEXT PRIMARY KEY, persona_id TEXT, mtype TEXT, text TEXT, ts REAL,
  valence REAL DEFAULT 0, arousal REAL DEFAULT 0, salience REAL DEFAULT 0.5, meta TEXT DEFAULT '{}', abstracted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS edge(src TEXT, dst TEXT, dim TEXT, w REAL, PRIMARY KEY(src,dst,dim));
CREATE TABLE IF NOT EXISTS checkpoint(task_id TEXT, step INTEGER, ts REAL, state TEXT, sha TEXT, PRIMARY KEY(task_id,step));
CREATE INDEX IF NOT EXISTS node_p ON node(persona_id, mtype, ts);
"""

def _tok(s):
    # crude RU/EN stemming: 4-char prefixes (машина/машины/машину -> "маши")
    return [t[:4] for t in re.findall(r"\w+", s.lower()) if len(t) > 2]

def _id(*parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]

class GraphMemory:
    def __init__(self, path=":memory:", clock=time.time, working_capacity=7):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.clock, self.wcap = clock, working_capacity

    # ---- online writer (fast path, called per turn) ----
    def write(self, persona_id, text, mtype="episodic", valence=0.0, arousal=0.0, salience=0.5, meta=None, relates_to=()):
        assert mtype in MEM_TYPES, mtype
        ts = self.clock(); nid = _id(persona_id, mtype, text, ts)
        self.db.execute("INSERT OR REPLACE INTO node VALUES(?,?,?,?,?,?,?,?,?,0)",
                        (nid, persona_id, mtype, text, ts, valence, arousal, salience, json.dumps(meta or {}, ensure_ascii=False)))
        prev = self.db.execute("SELECT id FROM node WHERE persona_id=? AND mtype=? AND id<>? ORDER BY ts DESC LIMIT 1",
                               (persona_id, mtype, nid)).fetchone()
        if prev:
            self.link(prev[0], nid, "temporal", 1.0)
        if abs(valence) + arousal > 0.6:
            self.link(nid, nid, "affective", abs(valence) + arousal)
        for other in relates_to:
            self.link(nid, other, "relational", 1.0)
        if mtype == "working":
            self._trim_working(persona_id)
        self.db.commit()
        return nid

    def link(self, a, b, dim, w=1.0):
        assert dim in DIMENSIONS, dim
        self.db.execute("INSERT INTO edge VALUES(?,?,?,?) ON CONFLICT(src,dst,dim) DO UPDATE SET w=w+excluded.w", (a, b, dim, w))

    def _trim_working(self, pid):
        ids = [r[0] for r in self.db.execute("SELECT id FROM node WHERE persona_id=? AND mtype='working' ORDER BY ts DESC", (pid,))]
        for i in ids[self.wcap:]:
            self.db.execute("DELETE FROM node WHERE id=?", (i,)); self.db.execute("DELETE FROM edge WHERE src=? OR dst=?", (i, i))

    # ---- emotion-attended retrieval ----
    def recall(self, persona_id, query, k=5, mood=(0.0, 0.0), half_life_s=7 * 86400, types=MEM_TYPES):
        q = set(_tok(query)); now = self.clock(); out = []
        ph = ",".join("?" * len(types))
        for nid, mtype, text, ts, val, aro, sal in self.db.execute(
                f"SELECT id,mtype,text,ts,valence,arousal,salience FROM node WHERE persona_id=? AND mtype IN ({ph})", (persona_id, *types)):
            t = set(_tok(text)); lex = len(q & t) / (len(q) or 1)
            if lex == 0 and mtype != "working":
                continue
            rec = 0.5 ** ((now - ts) / half_life_s)
            aff = 1.0 - (abs(val - mood[0]) + abs(aro - mood[1])) / 4.0   # mood congruence in [0.5,1]
            deg = self.db.execute("SELECT COALESCE(SUM(w),0) FROM edge WHERE src=? OR dst=?", (nid, nid)).fetchone()[0]
            score = 0.5 * lex + 0.2 * rec + 0.15 * aff * (0.5 + abs(val) + aro) / 2.5 + 0.1 * sal + 0.05 * math.log1p(deg)
            out.append({"id": nid, "type": mtype, "text": text, "score": round(score, 4)})
        return sorted(out, key=lambda r: -r["score"])[:k]

    # ---- offline abstraction (idle / "dreaming", System 2) ----
    def consolidate(self, persona_id, min_support=2, max_facts=10):
        """Episodic -> semantic: recurring keywords across un-abstracted episodes become semantic facts with
        relational edges back to their sources. Extractive and deterministic (no LLM needed)."""
        rows = self.db.execute("SELECT id,text,valence FROM node WHERE persona_id=? AND mtype='episodic' AND abstracted=0", (persona_id,)).fetchall()
        if not rows:
            return {"facts": 0, "episodes": 0}
        df = Counter(); by = {}
        for nid, text, _ in rows:
            for t in set(_tok(text)):
                df[t] += 1; by.setdefault(t, []).append(nid)
        made = 0
        for term, n in df.most_common():
            if n < min_support or made >= max_facts:
                break
            src = by[term]
            val = sum(r[2] for r in rows if r[0] in src) / len(src)
            fact = f"[abstraction] тема «{term}» встречалась в {n} эпизодах; средняя валентность {val:+.2f}"
            fid = self.write(persona_id, fact, "semantic", valence=val, salience=min(1.0, 0.4 + 0.1 * n))
            for s in src:
                self.link(fid, s, "semantic", 1.0)
            made += 1
        self.db.executemany("UPDATE node SET abstracted=1 WHERE id=?", [(r[0],) for r in rows])
        self.db.commit()
        return {"facts": made, "episodes": len(rows)}

    def add_procedure(self, persona_id, name, steps):
        return self.write(persona_id, f"{name}: " + " -> ".join(steps), "procedural", meta={"name": name, "steps": steps})

    # ---- checkpoint store for long tasks ----
    def checkpoint(self, task_id, step, state: dict):
        blob = json.dumps(state, ensure_ascii=False, sort_keys=True)
        sha = hashlib.sha256(blob.encode()).hexdigest()
        self.db.execute("INSERT OR REPLACE INTO checkpoint VALUES(?,?,?,?,?)", (task_id, step, self.clock(), blob, sha)); self.db.commit()
        return sha

    def resume(self, task_id):
        r = self.db.execute("SELECT step,state,sha FROM checkpoint WHERE task_id=? ORDER BY step DESC LIMIT 1", (task_id,)).fetchone()
        if not r:
            return None
        if hashlib.sha256(r[1].encode()).hexdigest() != r[2]:
            raise ValueError("checkpoint SHA mismatch")
        return {"step": r[0], "state": json.loads(r[1])}

    def forget_persona(self, persona_id):
        ids = [r[0] for r in self.db.execute("SELECT id FROM node WHERE persona_id=?", (persona_id,))]
        for i in ids:
            self.db.execute("DELETE FROM edge WHERE src=? OR dst=?", (i, i))
        self.db.execute("DELETE FROM node WHERE persona_id=?", (persona_id,)); self.db.commit()
        return len(ids)
