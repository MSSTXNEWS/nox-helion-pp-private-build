"""R2/sleep_feed.py: Growth -> ночной сон (SLP). Только проверенные решения (правила/исполнитель), без замороженных наборов, с потолком доли.

stage_for_sleep дописывает строки в state/feedback.jsonl (формат {q,a,v,t}, который читает SLP/build_kto.collect) с src='growth_*'.
leaks() - единая проверка «текст не из замороженного набора» (экзамен роста, MIND-BENCH holdout/dev): общая для сна и для gate_all.
"""
import hashlib
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "COMMON"), os.environ.get("NOX_COMMON", "")):
    if _p and os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)
import statefile
import anti_sycophancy as AS


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def shingles(text, k=5):
    w = re.findall(r"\w+", norm(text))
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))} or ({" ".join(w)} if w else set())


def build_frozen(texts):
    return [shingles(t) for t in texts if t and t.strip()]


def leaks(text, frozen, threshold=0.6):
    """True, если текст повторяет замороженное задание: >= threshold шинглов текста есть в задании ИЛИ >= threshold шинглов задания есть в тексте."""
    sh = shingles(text)
    if not sh:
        return False
    for f in frozen:
        if not f:
            continue
        inter = len(sh & f)
        if inter / len(sh) >= threshold or inter / len(f) >= threshold:
            return True
    return False


def _jl(p):
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for l in f:
                try:
                    out.append(json.loads(l))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def row_key(r):
    return hashlib.sha256((norm(r.get("q")) + "\x00" + norm(r.get("a")) + "\x00" + str(r.get("v"))).encode()).hexdigest()[:16]


def stage_for_sleep(growth, state_dir, since, frozen_texts=(), now=None, dry_run=False):
    """-> {rows, owner_rows, skipped_frozen, duplicates, path}. Потолок доли задаёт growth.sleep_batch (~30% смеси)."""
    fb = os.path.join(state_dir, "feedback.jsonl")
    existing = _jl(fb)
    owner_rows = sum(1 for r in existing if not str(r.get("src", "")).startswith("growth_") and (r.get("t") or 0) >= since)
    have = {row_key(r) for r in existing if str(r.get("src", "")).startswith("growth_")}
    frozen = build_frozen(frozen_texts)
    res = {"rows": 0, "owner_rows": owner_rows, "skipped_frozen": 0, "duplicates": 0, "path": fb}
    for r in growth.sleep_batch(since, owner_rows):
        if leaks(r.get("q", ""), frozen) or leaks(r.get("a", ""), frozen):
            res["skipped_frozen"] += 1
            continue
        k = row_key(r)
        if k in have:
            res["duplicates"] += 1
            continue
        have.add(k)
        if not dry_run:
            statefile.append_line(fb, json.dumps(r, ensure_ascii=False))
        res["rows"] += 1
    return res


# ------------------------------------------------------------------ предсказательное я -> сон (решение Создателя 22.11: обучать)
PREDICTIVE_MAX_SHARE = 0.3


def _outcomes(ps):
    """norm(реплика)[:120] -> проверяемый исход хода (bool) по эпизодам предсказательного я."""
    out = {}
    for e in (ps.s.get("episodes") or []) if ps is not None else []:
        o = (e.get("obs") or {}).get("outcome")
        if o is not None:
            out[norm(e.get("user_text"))[:120]] = bool(o)
    return out


def annotate_feedback(state_dir, ps=None, trace_dir=None, since=0, now=None):
    """Дописывает строкам Создателя (не growth_/predictive) в feedback.jsonl поля outcome (проверяемый исход или None) и disagree (NOX возразил по делу).
    Без исхода строка с 👍 станет approval_only в build_kto (пониженный вес, потолок 20%). Идемпотентно (уже размеченные не трогаются)."""
    fb = os.path.join(state_dir, "feedback.jsonl")
    rows = _jl(fb)
    if not rows:
        return {"annotated": 0}
    turns = {}
    for r in _jl(os.path.join(state_dir, "turns.jsonl")):
        if r.get("u") and r.get("a"):
            turns[norm(r["u"])[:120]] = r["a"]
    out_map, n = _outcomes(ps), 0
    for r in rows:
        src = str(r.get("src", ""))
        if src.startswith("growth_") or src == "predictive_self" or "disagree" in r or "outcome" in r:
            continue
        k = norm(r.get("q"))[:120]
        ans = r.get("a") or turns.get(k) or ""
        r["outcome"] = out_map.get(k)
        r["disagree"] = AS.is_pushback(ans)
        n += 1
    if n:
        tmp = fb + ".tmp"
        with statefile.locked(fb):
            with open(tmp, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, fb)
    return {"annotated": n}


def stage_predictive(ps, state_dir, since, frozen_texts=(), trace_dir=None, now=None, dry_run=False, min_surprise=0.65, max_share=PREDICTIVE_MAX_SHARE):
    """predictive_self.export_training_rows -> feedback.jsonl (src='predictive_self', v=1: наблюдённая реальность - эталон прогноза).
    Строка несёт outcome (проверяемый исход хода) и disagree (NOX возразил по делу в этом ходе): build_kto по ним ставит вес/потолок.
    Потолок: не более max_share от смеси (строки Создателя за окно). -> {rows, skipped_frozen, duplicates, cap}."""
    import tempfile
    fb = os.path.join(state_dir, "feedback.jsonl")
    existing = _jl(fb)
    owner = sum(1 for r in existing if not str(r.get("src", "")).startswith(("growth_", "predictive")) and (r.get("t") or 0) >= since)
    cap = int(max_share / (1 - max_share) * owner)
    res = {"rows": 0, "skipped_frozen": 0, "duplicates": 0, "cap": cap}
    if ps is None or cap <= 0 or dry_run:
        return res
    dmap = {r["turn_id"]: r["disagree"] for r in AS.turn_rows(state_dir, trace_dir, since, (now or 1e18) + 1) if r.get("turn_id")}
    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        os.remove(tmp)
        ps.export_training_rows(tmp, min_surprise=min_surprise, limit=cap)
        eps = {e["turn_id"]: e for e in ps.s.get("episodes", [])}
        have = {row_key(r) for r in existing if str(r.get("src", "")) == "predictive_self"}
        frozen = build_frozen(frozen_texts)
        for r in _jl(tmp):
            if leaks(r.get("instruction", ""), frozen):
                res["skipped_frozen"] += 1
                continue
            obs = (eps.get(r.get("turn_id")) or {}).get("obs") or {}
            row = {"q": r["instruction"], "a": r["output"], "v": 1, "t": now or 0, "src": "predictive_self", "turn_id": r.get("turn_id"),
                   "outcome": obs.get("outcome"), "disagree": bool(dmap.get(r.get("turn_id")))}
            if row_key(row) in have:
                res["duplicates"] += 1
                continue
            have.add(row_key(row))
            statefile.append_line(fb, json.dumps(row, ensure_ascii=False))
            res["rows"] += 1
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return res
