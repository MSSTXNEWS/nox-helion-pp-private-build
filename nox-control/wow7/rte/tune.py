"""RTE-11: журнал и самонастройка роутера (тихие часы). Читает журналы ходов хаба (state/rte/t-*.jsonl: meta/plan/delta/done),
считает p50/p90 TTFT и ток/с GLM и раз в сутки обновляет router_thresholds.json (think_budget_s, wait_budget_s) с обоснованием.
Правила: (1) только 23:00-08:00 МСК (--force для проверки); (2) порог минимума данных: >= MIN_TURNS ходов GLM за окно, иначе запись status=insufficient_data и файл НЕ меняется;
(3) A/B на последних 20 запросах: оффлайн-повтор route() со старыми и новыми порогами + оценка latency-fit (score_fn подменяется); новые пороги применяются,
только если средняя оценка не хуже старой (допуск EPS) - иначе status=rejected_ab; (4) предыдущий файл сохраняется как .prev (откат: --rollback).
Роутер читает файл через router.load_tuned() (rte_server подхватывает при старте и по mtime).
Запуск: python3 tune.py [--state DIR] [--out FILE] [--days 7] [--force] [--dry-run] [--rollback]
"""
import argparse, glob, json, math, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import router as R

for _c in (os.environ.get("NOX_COMMON", ""), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "COMMON"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "common")):
    if _c and os.path.isdir(_c) and _c not in sys.path:
        sys.path.append(_c)
import statefile
from quiet import in_quiet

MIN_TURNS, AB_N, EPS = 20, 20, 0.02
BOUNDS = {"think_budget_s": (20.0, 180.0), "wait_budget_s": (90.0, 600.0)}


def pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def read_turn(path):
    """-> dict хода или None: {id, t0, text, tier, plan, ttft_s, tps, total_s, status, deep_n}."""
    evs = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    evs.append(json.loads(ln))
                except ValueError:
                    break
    except OSError:
        return None
    if not evs:
        return None
    t0 = evs[0].get("t", 0.0)
    text, plan = "", {}
    for e in evs:
        if e.get("type") == "meta":
            text = e.get("text") or text
            plan = e.get("plan") or plan
    deep = [e for e in evs if e.get("type") == "delta" and e.get("stage") == "deep"]
    last = evs[-1]
    ttft = (deep[0]["t"] - t0) if deep else None
    tps = ((len(deep) - 1) / (deep[-1]["t"] - deep[0]["t"])) if len(deep) >= 3 and deep[-1]["t"] > deep[0]["t"] else None
    return {"id": os.path.basename(path)[:-6], "t0": t0, "text": text, "plan": plan, "tier": plan.get("tier"), "ttft_s": ttft, "tps": tps,
            "total_s": last.get("t", t0) - t0, "status": last.get("type"), "deep_n": len(deep)}


def load_turns(state_dir, now=None, days=7):
    now = time.time() if now is None else now
    out = []
    for p in sorted(glob.glob(os.path.join(state_dir, "t-*.jsonl"))):
        t = read_turn(p)
        if t and now - days * 86400 <= t["t0"] <= now:
            out.append(t)
    return out


def measure(turns):
    """Статистика только по успешным ходам GLM (done, был первый глубокий токен)."""
    g = [t for t in turns if t["status"] == "done" and t["ttft_s"] is not None]
    tt = [t["ttft_s"] for t in g]
    tp = [t["tps"] for t in g if t["tps"]]
    tot = [t["total_s"] for t in g]
    return {"n": len(g), "ttft_p50": pct(tt, 0.5), "ttft_p90": pct(tt, 0.9), "tps_p50": pct(tp, 0.5), "tps_p90": pct(tp, 0.9), "total_p90": pct(tot, 0.9)}


def _clamp(x, key):
    lo, hi = BOUNDS[key]
    return max(lo, min(hi, x))


def propose(m, answer_tokens=400):
    """Новые пороги по измеренному. think_budget: 1.5 * p50 TTFT (столько GLM реально думает), округление до 5 с;
    wait_budget: 1.2 * (p90 TTFT + ответ/ток/с p50), округление до 10 с."""
    think = _clamp(math.ceil(1.5 * m["ttft_p50"] / 5.0) * 5.0, "think_budget_s")
    tps = max(m["tps_p50"] or 0.5, 0.2)
    wait = _clamp(math.ceil(1.2 * (m["ttft_p90"] + answer_tokens / tps) / 10.0) * 10.0, "wait_budget_s")
    return {"think_budget_s": think, "wait_budget_s": wait}


def default_score(plan, turn):
    """Оценка плана на реальном ходе: 1 - относительная ошибка ETA, штраф за срезанный ответ (answer_capped) и за fast на сложном вопросе."""
    actual = max(turn.get("total_s") or 1.0, 1.0)
    s = 1.0 - min(1.0, abs(plan.eta_s - actual) / actual)
    if any(str(n).startswith("answer_capped") for n in plan.notes):
        s -= 0.25
    if plan.tier == "fast" and plan.features.get("code") and plan.features.get("reason"):
        s -= 0.3
    return max(0.0, s)


def ab_check(turns, old, new, score_fn=default_score, n=AB_N, tps=None):
    """Оффлайн A/B: route() со старым и новым RouterConfig на последних n ходах с текстом."""
    ts = [t for t in turns if t["text"]][-n:]
    if len(ts) < min(n, 5):
        return {"status": "insufficient_queries", "n": len(ts)}
    so = sn = 0.0
    for t in ts:
        dtps = t["tps"] or tps or 1.5
        so += score_fn(R.route(t["text"], deep_tps=dtps, cfg=old), t)
        sn += score_fn(R.route(t["text"], deep_tps=dtps, cfg=new), t)
    so, sn = so / len(ts), sn / len(ts)
    return {"status": "ok" if sn >= so - EPS else "worse", "n": len(ts), "score_old": round(so, 4), "score_new": round(sn, 4)}


def tune(state_dir, out, now=None, days=7, force=False, dry_run=False, score_fn=default_score):
    now = time.time() if now is None else now
    if not force and not in_quiet(now):
        return {"status": "skipped", "reason": "не тихие часы"}
    turns = load_turns(state_dir, now, days)
    m = measure(turns)
    if m["n"] < MIN_TURNS:
        return {"status": "insufficient_data", "measured": m["n"], "need": MIN_TURNS}
    cur = R.load_tuned(out) or {}
    old = R.RouterConfig(**{k: cur[k] for k in ("think_budget_s", "wait_budget_s") if k in cur})
    new_v = propose(m)
    new = R.RouterConfig(**new_v)
    if new_v == {"think_budget_s": old.think_budget_s, "wait_budget_s": old.wait_budget_s}:
        return {"status": "unchanged", "thresholds": new_v, "measured": m}
    ab = ab_check(turns, old, new, score_fn)
    res = {"status": "applied", "thresholds": new_v, "previous": {"think_budget_s": old.think_budget_s, "wait_budget_s": old.wait_budget_s}, "measured": m, "ab": ab, "ts": now,
           "basis": "think=1.5*p50 TTFT; wait=1.2*(p90 TTFT + 400/p50 ток/с)"}
    if ab["status"] != "ok":
        res["status"] = "rejected_ab"
        return res
    if not dry_run:
        if os.path.exists(out):
            shutil.copyfile(out, out + ".prev")
        statefile.save(out, dict(new_v, measured=m, ab=ab, ts=now, basis=res["basis"]))
    return res


def rollback(out):
    if not os.path.exists(out + ".prev"):
        return {"status": "nothing_to_rollback"}
    shutil.copyfile(out + ".prev", out)
    return {"status": "rolled_back"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=os.environ.get("RTE_STATE_DIR", "/root/nox/state/rte"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args(argv)
    out = a.out or os.path.join(a.state, "router_thresholds.json")
    r = rollback(out) if a.rollback else tune(a.state, out, days=a.days, force=a.force, dry_run=a.dry_run)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
