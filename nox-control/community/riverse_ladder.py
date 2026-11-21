"""riverse_ladder: лестница уверенности факта (SQLite, stdlib).

Уровни: 0 заметил -> 1 подозреваю -> 2 подтверждено -> 3 установлено.
Повышение: число НЕЗАВИСИМЫХ источников, тип источника, давность свидетельств.
Понижение: на 1 уровень за каждое противоречие. Все переходы в истории.
Импорт чатов: ChatGPT conversations.json, Claude conversations.json,
Gemini Takeout MyActivity.json -> кандидаты уровня «заметил».
"""
import json
import re
import sqlite3
import time

LEVELS = ["заметил", "подозреваю", "подтверждено", "установлено"]
DAY = 86400.0

DEFAULT_RULES = {
    "suspect_min_sources": 2,
    "confirm_min_sources": 3, "confirm_needs_strong": True,   # нужен owner/direct-источник
    "establish_min_sources": 5, "establish_min_kinds": 2, "establish_min_span_days": 7,
    "recency_days": 180,          # свидетельства старше не считаются
    "strong_kinds": ("owner", "direct"),
}


def norm_text(t):
    return re.sub(r"\s+", " ", t).strip().strip(".!?").casefold()


class Ladder:
    def __init__(self, path=":memory:", rules=None):
        self.rules = dict(DEFAULT_RULES, **(rules or {}))
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, key TEXT UNIQUE, text TEXT,
            level INTEGER DEFAULT 0, created REAL, updated REAL);
        CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY, fact_id INTEGER, source TEXT,
            kind TEXT, ts REAL, polarity INTEGER DEFAULT 1, UNIQUE(fact_id, source, polarity));
        CREATE TABLE IF NOT EXISTS transitions(id INTEGER PRIMARY KEY, fact_id INTEGER,
            from_level INTEGER, to_level INTEGER, reason TEXT, ts REAL);
        """)

    def close(self):
        self.db.close()

    # --- базовое ---
    def add_fact(self, text, ts=None):
        k = norm_text(text)
        r = self.db.execute("SELECT id FROM facts WHERE key=?", (k,)).fetchone()
        if r:
            return r[0]
        ts = ts or time.time()
        cur = self.db.execute("INSERT INTO facts(key,text,level,created,updated) VALUES(?,?,0,?,?)", (k, text.strip(), ts, ts))
        self.db.commit()
        return cur.lastrowid

    def level(self, fid):
        return self.db.execute("SELECT level FROM facts WHERE id=?", (fid,)).fetchone()[0]

    def level_name(self, fid):
        return LEVELS[self.level(fid)]

    def history(self, fid):
        return [(LEVELS[a], LEVELS[b], r) for a, b, r in self.db.execute(
            "SELECT from_level,to_level,reason FROM transitions WHERE fact_id=? ORDER BY id", (fid,))]

    def _set_level(self, fid, new, reason, ts):
        old = self.level(fid)
        if new == old:
            return False
        self.db.execute("UPDATE facts SET level=?, updated=? WHERE id=?", (new, ts, fid))
        self.db.execute("INSERT INTO transitions(fact_id,from_level,to_level,reason,ts) VALUES(?,?,?,?,?)",
                        (fid, old, new, reason, ts))
        self.db.commit()
        return True

    def add_evidence(self, fid, source, kind="chat", ts=None, evaluate=True):
        """Подтверждение из источника `source` (повтор того же источника не считается)."""
        ts = ts or time.time()
        self.db.execute("INSERT OR IGNORE INTO evidence(fact_id,source,kind,ts,polarity) VALUES(?,?,?,?,1)",
                        (fid, source, kind, ts))
        self.db.commit()
        return self.evaluate(fid, now=ts) if evaluate else self.level(fid)

    def contradict(self, fid, source, kind="chat", ts=None):
        """Противоречие: понижение на 1 уровень (минимум «заметил»), свидетельство «против»."""
        ts = ts or time.time()
        cur = self.db.execute("INSERT OR IGNORE INTO evidence(fact_id,source,kind,ts,polarity) VALUES(?,?,?,?,-1)",
                              (fid, source, kind, ts))
        self.db.commit()
        if cur.rowcount:
            self._set_level(fid, max(0, self.level(fid) - 1), "противоречие из %s" % source, ts)
        return self.level(fid)

    # --- правила повышения ---
    def _stats(self, fid, now):
        r = self.rules
        rows = self.db.execute("SELECT source,kind,ts FROM evidence WHERE fact_id=? AND polarity=1", (fid,)).fetchall()
        rows = [x for x in rows if now - x[2] <= r["recency_days"] * DAY]
        return rows

    def evaluate(self, fid, now=None):
        """Привести уровень в соответствие с правилами (вверх на сколько позволяют свидетельства;
        вниз, если свидетельства устарели). Возвращает уровень."""
        now = now or time.time()
        r = self.rules
        rows = self._stats(fid, now)
        # свидетельства, пришедшие после последнего противоречия
        last_neg = self.db.execute("SELECT MAX(ts) FROM evidence WHERE fact_id=? AND polarity=-1", (fid,)).fetchone()[0]
        if last_neg is not None:
            rows = [x for x in rows if x[2] > last_neg]
        sources = {x[0] for x in rows}
        kinds = {x[1] for x in rows}
        n = len(sources)
        strong = bool(kinds & set(r["strong_kinds"]))
        span = (max(x[2] for x in rows) - min(x[2] for x in rows)) / DAY if rows else 0
        target = 0
        if n >= r["suspect_min_sources"]:
            target = 1
            if n >= r["confirm_min_sources"] and (strong or not r["confirm_needs_strong"]):
                target = 2
                if n >= r["establish_min_sources"] and len(kinds) >= r["establish_min_kinds"] \
                        and span >= r["establish_min_span_days"]:
                    target = 3
        cur = self.level(fid)
        if target > cur:
            self._set_level(fid, target, "повышение: %d независимых источников, виды=%s, разброс %.1f дн" %
                            (n, sorted(kinds), span), now)
        elif target < cur:
            # свидетельства устарели/недостаточны (давность)
            self._set_level(fid, target, "понижение: свидетельств недостаточно/устарели (%d актуальных)" % n, now)
        return self.level(fid)

    def evaluate_all(self, now=None):
        return {fid: self.evaluate(fid, now) for (fid,) in self.db.execute("SELECT id FROM facts").fetchall()}

    def facts_at(self, level):
        return [r[0] for r in self.db.execute("SELECT text FROM facts WHERE level=? ORDER BY id", (level,))]

    def evidence_count(self, fid):
        return self.db.execute("SELECT COUNT(DISTINCT source) FROM evidence WHERE fact_id=? AND polarity=1", (fid,)).fetchone()[0]

    # --- импорт ---
    _FIRST = re.compile(r"\b(я|мне|меня|мой|моя|моё|мои|мы|i|i'm|i’m|i've|my|me|we)\b", re.I)

    @classmethod
    def candidates(cls, text, min_len=8, max_len=300):
        """Предложения от первого лица (кандидаты «заметил»)."""
        out = []
        for s in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
            s = s.strip()
            if min_len <= len(s) <= max_len and not s.endswith("?") and cls._FIRST.search(s):
                out.append(s)
        return out

    def _ingest(self, items):
        """items: (source, ts, text). Возвращает число добавленных/затронутых кандидатов."""
        n = 0
        for source, ts, text in items:
            for c in self.candidates(text):
                fid = self.add_fact(c, ts)
                self.add_evidence(fid, source, "import", ts, evaluate=False)
                n += 1
        return n

    @staticmethod
    def _load(src):
        if isinstance(src, (list, dict)):
            return src
        with open(src, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _parse_iso(s):
        from datetime import datetime, timezone
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        except Exception:
            return time.time()

    def import_chatgpt(self, src):
        data = self._load(src)
        items = []
        for conv in data:
            cid = conv.get("conversation_id") or conv.get("id") or conv.get("title", "?")
            for node in (conv.get("mapping") or {}).values():
                msg = node.get("message")
                if not msg or (msg.get("author") or {}).get("role") != "user":
                    continue
                parts = (msg.get("content") or {}).get("parts") or []
                text = "\n".join(p for p in parts if isinstance(p, str))
                items.append(("chatgpt:%s" % cid, msg.get("create_time") or conv.get("create_time") or time.time(), text))
        return self._ingest(items)

    def import_claude(self, src):
        data = self._load(src)
        if isinstance(data, dict):
            data = data.get("conversations", [])
        items = []
        for conv in data:
            cid = conv.get("uuid") or conv.get("name", "?")
            for m in conv.get("chat_messages", []):
                if m.get("sender") != "human":
                    continue
                text = m.get("text") or "\n".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")
                items.append(("claude:%s" % cid, self._parse_iso(m.get("created_at", "")), text))
        return self._ingest(items)

    def import_gemini(self, src):
        data = self._load(src)
        items = []
        for i, e in enumerate(data):
            title = e.get("title", "")
            m = re.match(r"(Prompted|Asked|Запрос:?)\s+(.*)", title, re.S)
            if not m:
                continue
            ts = self._parse_iso(e.get("time", ""))
            items.append(("gemini:%s" % (e.get("time") or i), ts, m.group(2)))
        return self._ingest(items)
