#!/usr/bin/env python3
"""speed_report.py: собирает SPEED_REPORT.json этапа S1_03 из результатов ab_bench.
Входы (все JSON из ab_bench/--attach): --before (замер живого GLM до), --after (замер после перезапуска), --ab (results.json прогона --accumulate),
--opt02 (OPT-02.json), --soul (JSON {cold_ttft_s, warm_ttft_s, mode}), --fast (опц. замер быстрой модели до/после как {before:{},after:{}}).
Вердикт: improved (score>=1.05 и качество >=0.9), neutral, regressed (tg после < 0.9 до ИЛИ качество < 0.9) -> rollback_recommended=true."""
import argparse
import difflib
import json
import sys
import time


def _metrics(path):
    if not path:
        return None
    d = json.load(open(path, encoding="utf-8"))
    if "winner" in d and isinstance(d["winner"], dict) and d["winner"].get("metrics"):
        return d["winner"]["metrics"]
    if d.get("results"):
        r = d["results"][0]
        return r.get("metrics")
    return d.get("metrics")


def _pick(m):
    return {k: (round(m[k], 3) if isinstance(m.get(k), (int, float)) else m.get(k)) for k in ("tg", "pp", "ttft_short_s", "ttft_long_s")} if m else None


def _x(a, b, inv=False):
    if not a or not b:
        return None
    return round((a / b) if inv else (b / a), 3)


def build(before, after, ab=None, opt02=None, soul=None, fast=None, targets=None):
    rep = {"id": "SPEED_REPORT", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "before": _pick(before), "after": _pick(after)}
    gain = {}
    if before and after:
        gain = {"tg_x": _x(before.get("tg"), after.get("tg")), "pp_x": _x(before.get("pp"), after.get("pp")),
                "ttft_short_x": _x(before.get("ttft_short_s"), after.get("ttft_short_s"), inv=True),
                "ttft_long_x": _x(before.get("ttft_long_s"), after.get("ttft_long_s"), inv=True)}
        sim = difflib.SequenceMatcher(None, before.get("quality_text") or "", after.get("quality_text") or "").ratio()
        rep["quality_similarity_after_vs_before"] = round(sim, 3)
    else:
        sim = None
    rep["gain"] = gain
    lv = []
    if ab:
        for r in ab.get("results", []):
            m, v = r.get("metrics") or {}, r.get("verdict") or {}
            lv.append({"id": r["id"], "status": "skip" if r.get("skip") else ("ok" if r.get("ok") else "fail"),
                       "tg": m.get("tg"), "pp": m.get("pp"), "ttft_short_s": m.get("ttft_short_s"),
                       "score": round(v["score"], 3) if v.get("score") else None, "accepted": v.get("accepted"),
                       "why": r.get("skip") or r.get("error") or "; ".join(v.get("reasons", []))})
        w = ab.get("winner") or {}
        rep["winner"] = {"id": w.get("id"), "args": w.get("args"), "env": w.get("env")}
    rep["levers"] = lv
    if opt02:
        rep["opt02"] = {k: opt02.get(k) for k in ("worth_draft", "why", "n", "ratio", "ok")}
    if soul:
        c, w_ = soul.get("cold_ttft_s"), soul.get("warm_ttft_s")
        rep["soul_kv"] = {"cold_ttft_s": c, "warm_ttft_s": w_, "speedup_x": _x(w_, c) if c and w_ else None, "mode": soul.get("mode")}
    if fast:
        rep["fast_tier"] = fast
    t = targets or {"tg_min": 3.0}
    rep["targets"] = {"tg_ge_plan": bool(after and after.get("tg") and after["tg"] >= t["tg_min"]), "tg_min": t["tg_min"]}
    verdict, why = "neutral", []
    if not (before and after):
        verdict, why = "no_data", ["нет замера до или после"]
    else:
        if after.get("tg") and before.get("tg") and after["tg"] < before["tg"] * 0.9:
            why.append("tg после на >10%% ниже (%.2f < %.2f)" % (after["tg"], before["tg"]))
        if sim is not None and sim < 0.9:
            why.append("качество: сходство %.2f < 0.9" % sim)
        score = 1.0
        parts = [(gain.get("tg_x"), 0.6), (gain.get("pp_x"), 0.3), (gain.get("ttft_short_x"), 0.1)]
        for g, wt in parts:
            if g:
                score *= g ** wt
        rep["score"] = round(score, 3)
        verdict = "regressed" if why else ("improved" if score >= 1.05 else "neutral")
    rep["verdict"], rep["why"] = verdict, why
    rep["rollback_recommended"] = verdict == "regressed"
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for n in ("before", "after", "ab", "opt02", "soul", "fast"):
        ap.add_argument("--" + n, default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ld = lambda p: json.load(open(p, encoding="utf-8")) if p else None  # noqa: E731
    rep = build(_metrics(a.before) if a.before else None, _metrics(a.after) if a.after else None, ld(a.ab), ld(a.opt02), ld(a.soul), ld(a.fast))
    json.dump(rep, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("verdict=%s score=%s gain=%s rollback=%s" % (rep["verdict"], rep.get("score"), json.dumps(rep["gain"]), rep["rollback_recommended"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
