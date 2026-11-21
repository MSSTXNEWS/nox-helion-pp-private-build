"""D04-22 «на чём остановились?»: ответ по сохранённой сводке последней сессии, без вызова модели.
Источник: JSONL (по строке на сессию) или SQLite (таблица sessions). Поля: ts, summary, open_items (список/текст/JSON), next_step, last_user."""
import json, re, sqlite3, os
RESUME_RE = re.compile(r"на\s+чем\s+(?:мы\s+)?остановил\w*|где\s+(?:мы\s+)?остановил\w*|что\s+мы\s+(?:делали|обсуждали)\s+(?:в\s+)?(?:прошлый|последний)|продолжим\s+с\s+того|remind me where we left|where did we leave off", re.I)

def is_resume_query(text): return bool(RESUME_RE.search((text or "").replace("ё", "е")))

def _items(v):
    if v is None or v == "": return []
    if isinstance(v, list): return [str(x) for x in v if str(x).strip()]
    if isinstance(v, str):
        try:
            j = json.loads(v)
            if isinstance(j, list): return [str(x) for x in j]
        except Exception: pass
        return [s.strip(" -•") for s in v.splitlines() if s.strip()]
    return [str(v)]

def load_last(path):
    """Последняя сессия по ts (либо последняя запись). None если нет источника/пусто."""
    if not path or not os.path.exists(path): return None
    rows = []
    if path.endswith((".db", ".sqlite", ".sqlite3")):
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        try:
            c.row_factory = sqlite3.Row
            rows = [dict(r) for r in c.execute("SELECT * FROM sessions ORDER BY ts DESC LIMIT 1")]
        finally: c.close()
    else:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try: rows.append(json.loads(line))
                    except Exception: pass
        rows.sort(key=lambda r: str(r.get("ts", "")))
        rows = rows[-1:]
    return rows[0] if rows else None

def resume_answer(path):
    r = load_last(path)
    if not r: return "Сохранённой сводки последней сессии нет, поэтому сказать, на чём остановились, не могу."
    out = []
    ts = r.get("ts")
    out.append("Последняя сессия%s: %s" % (" (%s)" % ts if ts else "", str(r.get("summary") or r.get("topic") or "без сводки").strip()))
    items = _items(r.get("open_items"))
    if items: out.append("Не закончено:\n" + "\n".join("- " + i for i in items[:7]))
    if r.get("next_step"): out.append("Следующий шаг: " + str(r["next_step"]).strip())
    elif r.get("last_user"): out.append("Последняя твоя реплика: " + str(r["last_user"]).strip())
    return "\n".join(out)
