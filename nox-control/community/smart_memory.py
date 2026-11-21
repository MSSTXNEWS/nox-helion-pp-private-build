"""smart_memory: карта «кто что знает/скрывает», проверка противоречий, «В прошлый раз...».

SQLite, только stdlib. Утверждения - тройки subject-predicate-value.
Предполагается, что предикат однозначный (одно значение), если он не
зарегистрирован как multi через set_multi().
"""
import re
import sqlite3
import time

KNOWN, SECRET = "known", "secret"

_CLAIM_RES = [
    re.compile(r"(?P<s>[\w\- ]+?)\.(?P<p>[\w\-]+)\s*=\s*(?P<v>[^\n;]+)"),          # subj.pred = value
    re.compile(r"(?P<s>[\w\-]+):\s*(?P<p>[\w\- ]+?)\s*=\s*(?P<v>[^\n;]+)"),         # subj: pred = value
]


def norm(x):
    return re.sub(r"\s+", " ", str(x)).strip().strip(".").casefold()


def extract_claims(text):
    """Вернуть [(subject, predicate, value, span)] из текста формата
    'subj.pred = value' или 'subj: pred = value'."""
    out, seen = [], []
    for rx in _CLAIM_RES:
        for m in rx.finditer(text):
            if any(m.start() < e and m.end() > s for s, e in seen):
                continue
            seen.append((m.start(), m.end()))
            a, b = m.span("v")
            while b > a and text[b - 1] in " \t.,!?":
                b -= 1
            out.append((m.group("s").strip(), m.group("p").strip(), text[a:b], (a, b)))
    out.sort(key=lambda c: c[3][0])
    return out


class SmartMemory:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, subject TEXT, predicate TEXT,
            value TEXT, visibility TEXT DEFAULT 'known', ts REAL, source TEXT);
        CREATE TABLE IF NOT EXISTS knows(fact_id INTEGER, who TEXT, UNIQUE(fact_id, who));
        CREATE TABLE IF NOT EXISTS multi(predicate TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY, topic TEXT, summary TEXT, ts REAL);
        """)

    def close(self):
        self.db.close()

    # --- карта знаний ---
    def add_fact(self, subject, predicate, value, visibility=KNOWN, knows=(), ts=None, source=None):
        if visibility not in (KNOWN, SECRET):
            raise ValueError("visibility must be known|secret")
        cur = self.db.execute(
            "INSERT INTO facts(subject,predicate,value,visibility,ts,source) VALUES(?,?,?,?,?,?)",
            (norm(subject), norm(predicate), str(value).strip(), visibility, ts or time.time(), source))
        fid = cur.lastrowid
        for w in knows:
            self.db.execute("INSERT OR IGNORE INTO knows VALUES(?,?)", (fid, norm(w)))
        self.db.commit()
        return fid

    def set_multi(self, predicate):
        self.db.execute("INSERT OR IGNORE INTO multi VALUES(?)", (norm(predicate),)); self.db.commit()

    def share(self, fact_id, who):
        self.db.execute("INSERT OR IGNORE INTO knows VALUES(?,?)", (fact_id, norm(who))); self.db.commit()

    def set_visibility(self, fact_id, visibility):
        self.db.execute("UPDATE facts SET visibility=? WHERE id=?", (visibility, fact_id)); self.db.commit()

    def who_knows(self, fact_id):
        return [r[0] for r in self.db.execute("SELECT who FROM knows WHERE fact_id=? ORDER BY who", (fact_id,))]

    def facts_about(self, subject, viewer=None):
        """Факты о субъекте. known - видны всем; secret - только тем, кто в knows.
        viewer=None - полный (внутренний) доступ."""
        rows = self.db.execute("SELECT id,predicate,value,visibility FROM facts WHERE subject=? ORDER BY id",
                               (norm(subject),)).fetchall()
        if viewer is None:
            return rows
        v = norm(viewer)
        return [r for r in rows if r[3] == KNOWN or v in self.who_knows(r[0])]

    def secrets(self):
        return self.db.execute("SELECT id,subject,predicate,value FROM facts WHERE visibility='secret'").fetchall()

    def knowledge_map(self):
        """{who: [fact_id,...]} - карта «кто что знает»."""
        m = {}
        for fid, who in self.db.execute("SELECT fact_id, who FROM knows ORDER BY fact_id"):
            m.setdefault(who, []).append(fid)
        return m

    # --- противоречия ---
    def _is_multi(self, predicate):
        return self.db.execute("SELECT 1 FROM multi WHERE predicate=?", (norm(predicate),)).fetchone() is not None

    def find_contradictions(self, text):
        """[{subject,predicate,new,stored,fact_id,span}] для утверждений текста,
        противоречащих сохранённым (однозначные предикаты)."""
        res = []
        for s, p, v, span in extract_claims(text):
            if self._is_multi(p):
                continue
            rows = self.db.execute("SELECT id,value FROM facts WHERE subject=? AND predicate=? ORDER BY ts DESC,id DESC",
                                   (norm(s), norm(p))).fetchall()
            if not rows or norm(rows[0][1]) == norm(v):
                continue
            res.append({"subject": s, "predicate": p, "new": v, "stored": rows[0][1],
                        "fact_id": rows[0][0], "span": span})
        return res

    def autocorrect(self, text):
        """(исправленный_текст, список_противоречий): значения подменяются сохранёнными."""
        cs = self.find_contradictions(text)
        for c in sorted(cs, key=lambda c: c["span"][0], reverse=True):
            a, b = c["span"]
            text = text[:a] + c["stored"] + text[b:]
        return text, cs

    # --- «В прошлый раз...» ---
    def record_topic(self, topic, summary="", ts=None):
        self.db.execute("INSERT INTO topics(topic,summary,ts) VALUES(?,?,?)", (topic, summary, ts or time.time()))
        self.db.commit()

    def recall_last(self, now=None, pause_threshold=6 * 3600, max_phrases=2):
        """Если с последней записанной темы прошло > порога - 1-2 фразы-напоминания, иначе []."""
        now = now or time.time()
        rows = self.db.execute("SELECT topic,summary,ts FROM topics ORDER BY ts DESC, id DESC LIMIT 2").fetchall()
        if not rows or now - rows[0][2] <= pause_threshold:
            return []
        t, s, ts = rows[0]
        phrases = ["В прошлый раз мы говорили про «%s»." % t]
        if s:
            phrases.append("Остановились на том, что %s" % s.rstrip(".") + ".")
        elif len(rows) > 1:
            phrases.append("Перед этим обсуждали «%s»." % rows[1][0])
        return phrases[:max_phrases]
