"""Библиотека навыков (шаг 35): успешное решение -> рецепт (JSON: условие, шаги, инструменты, проверка), поиск по описанию (SQLite FTS5), подстановка в промпт.
Рецепт: {"id","name","condition","steps":[...],"tools":[...],"check","source_task","uses","successes","created","updated"}. Секреты при сохранении вычищаются."""
import json, os, re, sqlite3, sys, time, hashlib

SECRET = re.compile(r"(?i)(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|(?:token|password|passwd|secret|api[_-]?key)\"?\s*[:=]\s*\"?[^\s\",}]{6,})")
WORD = re.compile(r"[\w]+", re.U)
STOP = {"и", "в", "на", "с", "по", "к", "из", "для", "что", "как", "это", "не", "а", "the", "a", "of", "to", "in", "and", "for", "is"}


def terms(text, prefix=True):
    """Слова для FTS: нижний регистр, ё->е, стоп-слова прочь; для русского грубая основа (до 6 символов) под префиксный поиск."""
    out = []
    for w in WORD.findall((text or "").lower().replace("ё", "е")):
        if len(w) < 2 or w in STOP: continue
        out.append(w[:6] if prefix and len(w) > 6 else w)
    return out


def fts_query(text):
    ts = list(dict.fromkeys(terms(text)))
    return " OR ".join('"%s"*' % t.replace('"', "") for t in ts[:24])


def _scrub(v):
    if isinstance(v, str): return SECRET.sub("[секрет скрыт]", v)
    if isinstance(v, list): return [_scrub(x) for x in v]
    return v


class SkillLibrary:
    def __init__(self, path):
        self.path = path
        if path != ":memory:": os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
        self.db.execute("CREATE TABLE IF NOT EXISTS skills(id TEXT PRIMARY KEY, name TEXT, condition TEXT, steps TEXT, tools TEXT, check_text TEXT, source_task TEXT, "
                        "uses INTEGER DEFAULT 0, successes INTEGER DEFAULT 0, created REAL, updated REAL, body TEXT)")
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(id UNINDEXED, name, condition, steps, tools, check_text, tokenize='unicode61 remove_diacritics 2')")
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        self.db.commit()

    # ---- запись
    def save(self, recipe):
        r = dict(recipe)
        name = _scrub(str(r.get("name") or r.get("condition") or "").strip())[:120]
        cond = _scrub(str(r.get("condition") or name).strip())[:500]
        if not name or not r.get("steps"): raise ValueError("рецепт без имени или шагов")
        steps = [str(_scrub(s))[:300] for s in r["steps"]][:40]
        tools = sorted({str(t) for t in r.get("tools", [])})
        check = _scrub(str(r.get("check") or ""))[:300]
        rid = r.get("id") or hashlib.sha1((re.sub(r"\s+", " ", name.lower()) + "|" + cond.lower()).encode()).hexdigest()[:12]
        now = time.time()
        old = self.db.execute("SELECT * FROM skills WHERE id=?", (rid,)).fetchone()
        body = json.dumps({"id": rid, "name": name, "condition": cond, "steps": steps, "tools": tools, "check": check, "source_task": str(r.get("source_task") or "")[:200]}, ensure_ascii=False)
        if old:
            self.db.execute("UPDATE skills SET name=?,condition=?,steps=?,tools=?,check_text=?,source_task=?,updated=?,body=?,successes=successes+1 WHERE id=?",
                            (name, cond, json.dumps(steps, ensure_ascii=False), json.dumps(tools), check, r.get("source_task"), now, body, rid))
        else:
            self.db.execute("INSERT INTO skills(id,name,condition,steps,tools,check_text,source_task,uses,successes,created,updated,body) VALUES(?,?,?,?,?,?,?,0,1,?,?,?)",
                            (rid, name, cond, json.dumps(steps, ensure_ascii=False), json.dumps(tools), check, r.get("source_task"), now, now, body))
        if self.fts:
            self.db.execute("DELETE FROM skills_fts WHERE id=?", (rid,))
            self.db.execute("INSERT INTO skills_fts(id,name,condition,steps,tools,check_text) VALUES(?,?,?,?,?,?)",
                            (rid, " ".join(terms(name, False)), " ".join(terms(cond, False)), " ".join(terms(" ".join(steps), False)), " ".join(tools), " ".join(terms(check, False))))
        self.db.commit()
        return rid

    def from_run(self, task, records, summary="", check=None):
        """Строит рецепт из журнала успешного прогона (records = строки Journal): шаги = удавшиеся вызовы инструментов по порядку."""
        steps, tools, last_check = [], [], check
        for r in records:
            if r.get("kind") != "tool" or r.get("name") == "finish" or not r.get("ok"): continue
            a = r.get("args") or {}
            brief = a.get("cmd") or a.get("path") or a.get("query") or a.get("url") or a.get("action") or ""
            line = "%s(%s)" % (r["name"], str(brief)[:100])
            if not steps or steps[-1] != line: steps.append(line)
            tools.append(r["name"])
            if r["name"] == "run_tests": last_check = "run_tests " + str(a.get("cmd") or "по умолчанию") + " -> зелёные"
        if not steps: return None
        title = task.get("title") if isinstance(task, dict) else str(task)
        return {"name": title, "condition": (title + ". " + str(summary))[:500], "steps": steps, "tools": tools, "check": last_check or "", "source_task": title}

    def save_from_run(self, task, records, summary="", check=None):
        r = self.from_run(task, records, summary, check)
        return self.save(r) if r else None

    # ---- поиск
    def get(self, rid):
        row = self.db.execute("SELECT * FROM skills WHERE id=?", (rid,)).fetchone()
        return self._row(row) if row else None

    @staticmethod
    def _row(row):
        return {"id": row["id"], "name": row["name"], "condition": row["condition"], "steps": json.loads(row["steps"]), "tools": json.loads(row["tools"]), "check": row["check_text"],
                "uses": row["uses"], "successes": row["successes"], "source_task": row["source_task"]}

    def search(self, query, k=3):
        q = fts_query(query)
        if not q: return []
        ids = []
        if self.fts:
            try:
                ids = [r["id"] for r in self.db.execute("SELECT id FROM skills_fts WHERE skills_fts MATCH ? ORDER BY bm25(skills_fts, 0, 4.0, 3.0, 1.0, 0.5, 0.5) LIMIT ?", (q, k))]
            except sqlite3.OperationalError:
                ids = []
        if not ids:       # без FTS5: подсчёт совпавших основ
            ts = terms(query)
            scored = []
            for row in self.db.execute("SELECT * FROM skills"):
                hay = (row["name"] + " " + row["condition"] + " " + row["steps"]).lower().replace("ё", "е")
                s = sum(1 for t in ts if t in hay)
                if s: scored.append((s, row["id"]))
            ids = [i for _s, i in sorted(scored, reverse=True)[:k]]
        return [self.get(i) for i in ids]

    def record_use(self, rid, success):
        self.db.execute("UPDATE skills SET uses=uses+1, successes=successes+? WHERE id=?", (1 if success else 0, rid))
        self.db.commit()

    @staticmethod
    def render_prompt(recipes, max_chars=2500):
        """Текст для подстановки в промпт; ограничен по длине."""
        out, n = [], 0
        for r in recipes:
            blk = "Рецепт «%s» (когда: %s)\n%s\nПроверка: %s" % (r["name"], r["condition"][:200], "\n".join("  %d. %s" % (i + 1, s) for i, s in enumerate(r["steps"][:12])), r["check"] or "нет")
            if n + len(blk) > max_chars: break
            out.append(blk); n += len(blk)
        return "\n\n".join(out)

    def prompt_for(self, task_text, k=2, max_chars=2500):
        return self.render_prompt(self.search(task_text, k), max_chars)


def main(argv=None):
    from .config import Config
    a = list(sys.argv[1:] if argv is None else argv)
    lib = SkillLibrary(Config().skills_db)
    if len(a) >= 2 and a[0] == "search":
        for r in lib.search(" ".join(a[1:])): print("%s\t%s\t%d шагов" % (r["id"], r["name"], len(r["steps"])))
        return 0
    print("usage: skills search <описание>"); return 2


if __name__ == "__main__":
    sys.exit(main())
