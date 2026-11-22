"""core_view: данные для страницы «Ядро» (веб рисует сам, здесь только API): список ходов, сводка, один ход со ступенями.
GET /v1/core/traces?limit=30&path=&eval=0|1  -> [{id, ts, user, path, arm, model, verdict, total_ms, recall_n, council, degraded, status}]
GET /v1/core/summary?limit=200                -> агрегаты: пути, вердикты Совести, медианы, Совет, деградации, ошибки исполнителей, V0
GET /v1/core/trace/<id>                       -> полная трасса (уже есть); view(trace) - то же, но со ступенями по порядку для таймлайна.
Только чтение: ни трассы, ни состояние не меняются. Ходы бенчмарка (trace.eval) скрыты, пока не просят eval=1."""
import json
import os
import re
import statistics

MAX_LIMIT = 500


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def summarize(tr):
    c = tr.get("council") or {}
    return {"id": tr.get("turn_id"), "ts": tr.get("started"), "user": (tr.get("user_text") or "")[:80], "status": tr.get("status"),
            "path": tr.get("path"), "path_code": tr.get("path_code"), "arm": tr.get("arm"), "model": tr.get("model"),
            "verdict": (tr.get("conscience") or {}).get("verdict"), "findings": len((tr.get("conscience") or {}).get("findings") or []),
            "total_ms": tr.get("total_ms"), "recall_n": tr.get("recall_n", 0), "degraded": list(tr.get("degraded") or []),
            "council": {"n": c.get("n", 0), "advisors": list(c.get("advisors") or [])} if c else None, "eval": bool(tr.get("eval")),
            "errors": len(tr.get("errors") or [])}


def view(tr):
    """Одна трасса для таймлайна: ступени конвейера по порядку (имя, статус, мс), Совесть, Совет."""
    steps = [{"name": r.get("name"), "status": r.get("status", "ok" if "ms" in r else "running"), "ms": r.get("ms"), "note": (r.get("note") or r.get("error") or "")[:160]}
             for r in tr.get("executors") or []]
    out = summarize(tr)
    out.update(steps=steps, conscience=tr.get("conscience") or {}, council=tr.get("council"), phases=tr.get("phases") or [], errors=tr.get("errors") or [])
    return out


def _disk_traces(trace_dir, limit):
    if not trace_dir or not os.path.isdir(trace_dir):
        return []
    try:
        files = sorted((f for f in os.scandir(trace_dir) if f.name.endswith(".json")), key=lambda f: f.stat().st_mtime, reverse=True)[:limit * 2]
    except OSError:
        return []
    out = []
    for f in files:
        try:
            with open(f.path, encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d, dict) and d.get("turn_id"):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def recent(core, limit=30, path=None, with_eval=False):
    limit = max(1, min(int(limit or 30), MAX_LIMIT))
    seen, rows = set(), []
    for tr in [t.trace for t in list(core.turns.values())] + _disk_traces(getattr(core.cfg, "trace_dir", ""), limit):
        tid = tr.get("turn_id")
        if tid in seen:
            continue
        seen.add(tid)
        if tr.get("eval") and not with_eval:
            continue
        if path and path not in (tr.get("path"), tr.get("path_code")):
            continue
        rows.append(summarize(tr))
    rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
    return rows[:limit]


def _counter(vals):
    out = {}
    for v in vals:
        if v:
            out[str(v)] = out.get(str(v), 0) + 1
    return out


def summary(core, limit=200, v0=None):
    rows = recent(core, limit)
    ms = [r["total_ms"] for r in rows if _num(r.get("total_ms")) is not None]
    deg = [d for r in rows for d in r["degraded"]]
    res = {"turns": len(rows), "paths": _counter(r["path"] for r in rows), "verdicts": _counter(r["verdict"] for r in rows),
           "status": _counter(r["status"] for r in rows), "degraded": _counter(deg),
           "total_ms": {"p50": int(statistics.median(ms)), "p90": int(sorted(ms)[int(0.9 * (len(ms) - 1))]), "max": max(ms)} if ms else None,
           "council_turns": sum(1 for r in rows if r["council"]), "recall_avg": round(sum(r["recall_n"] or 0 for r in rows) / len(rows), 2) if rows else 0,
           "with_errors": sum(1 for r in rows if r["errors"]), "conscience_mode": getattr(getattr(core, "conscience", None), "mode", None)}
    if v0 is not None:
        res["v0"] = v0
    return res


def query_int(qs, key, default):
    m = re.search(r"(?:^|&)%s=(\d+)" % key, qs or "")
    return int(m.group(1)) if m else default


def query_str(qs, key):
    m = re.search(r"(?:^|&)%s=([\w.-]{1,40})" % key, qs or "")
    return m.group(1) if m else None
