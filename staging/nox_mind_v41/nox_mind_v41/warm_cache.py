"""WarmS03Cache: LRU+TTL cache over a scoped FTS5 index; invalidation by PersonaID (generation counters)."""
import sqlite3, time, threading, re
from collections import OrderedDict

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(id UNINDEXED, persona_id UNINDEXED, scope UNINDEXED, text, tokenize='unicode61');
"""

def _norm(q: str) -> str:
    return " ".join(re.findall(r"\w+", q.lower()))

class ScopedFTS:
    """FTS5 index where every row carries persona_id + scope ('session:<id>', 'persona', 'global')."""
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self._lock = threading.Lock()

    def add(self, item_id, persona_id, scope, text):
        with self._lock:
            self.db.execute("INSERT INTO mem_fts(id,persona_id,scope,text) VALUES(?,?,?,?)", (item_id, persona_id, scope, text))
            self.db.commit()

    def delete_persona(self, persona_id):
        with self._lock:
            self.db.execute("DELETE FROM mem_fts WHERE persona_id=?", (persona_id,)); self.db.commit()

    def search(self, query, persona_id, scopes=("global", "persona"), k=6):
        terms = _norm(query).split()
        if not terms:
            return []
        match = " OR ".join('"%s"' % t for t in terms)
        ph = ",".join("?" * len(scopes))
        sql = (f"SELECT id, scope, text, bm25(mem_fts) AS s FROM mem_fts WHERE mem_fts MATCH ? "
               f"AND (persona_id=? OR scope='global') AND scope IN ({ph}) ORDER BY s LIMIT ?")
        with self._lock:
            rows = self.db.execute(sql, (match, persona_id, *scopes, k)).fetchall()
        return [{"id": r[0], "scope": r[1], "text": r[2], "score": -r[3]} for r in rows]

class WarmS03Cache:
    def __init__(self, fts: ScopedFTS, max_items=512, ttl_s=300.0, clock=time.monotonic):
        self.fts, self.max, self.ttl, self.clock = fts, max_items, ttl_s, clock
        self._c = OrderedDict(); self._gen = {}; self.hits = self.misses = 0
        self._lock = threading.Lock()

    def _key(self, persona_id, scopes, query):
        return (persona_id, self._gen.get(persona_id, 0), tuple(scopes), _norm(query))

    def recall(self, query, persona_id, scopes=("global", "persona"), k=6):
        key = self._key(persona_id, scopes, query)
        with self._lock:
            hit = self._c.get(key)
            if hit and self.clock() - hit[0] < self.ttl:
                self._c.move_to_end(key); self.hits += 1
                return hit[1]
        res = self.fts.search(query, persona_id, scopes, k)
        with self._lock:
            self.misses += 1
            self._c[key] = (self.clock(), res); self._c.move_to_end(key)
            while len(self._c) > self.max:
                self._c.popitem(last=False)
        return res

    def write(self, item_id, persona_id, scope, text):
        """Write-through: index + invalidate that persona's warm entries."""
        self.fts.add(item_id, persona_id, scope, text)
        self.invalidate_persona(persona_id)

    def invalidate_persona(self, persona_id):
        with self._lock:
            self._gen[persona_id] = self._gen.get(persona_id, 0) + 1
            for k in [k for k in self._c if k[0] == persona_id]:
                del self._c[k]

    def stats(self):
        n = self.hits + self.misses
        return {"items": len(self._c), "hits": self.hits, "misses": self.misses, "hit_rate": (self.hits / n) if n else 0.0}
