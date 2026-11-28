#!/usr/bin/env python3
"""Бэктест модели собеседника на реальных диалогах (web_conv): прогноз реакции на ответ NOX против лексической оценки следующей реплики человека. Печатает только числа."""
import sys, os, json, glob, collections
sys.path.insert(0, "/workspace/nox/mods")
import interlocutor_model as im
m = im.Model("creator"); base = collections.Counter(); hit = 0; n = 0; early = []; late = []; seq = []
for f in sorted(glob.glob("/workspace/nox/state/web/web_conv/*.json")):
    if "/qa-" in f: continue
    try: d = json.load(open(f, encoding="utf-8"))
    except Exception: continue
    ms = d.get("messages") or []
    for i in range(len(ms) - 1):
        a, u = ms[i], ms[i + 1]
        if a.get("role") in ("assistant", "nox") and u.get("role") == "user" and a.get("content") and u.get("content"):
            ts = float(u.get("ts") or 0) or 1.0
            seq.append((ts, a["content"], u["content"]))
seq.sort(key=lambda x: x[0])
for ts, a, u in seq:
    m.update({"ts": ts, "text": u, "user": "creator"})
    fc = m.forecast(a, ts); lab_obs = "доволен" if im.lexical_pad(u)["v"] > 0.2 else ("раздражение" if im.lexical_pad(u)["v"] < -0.2 else "нейтрально")
    r = m.observe(a, u, ts); n += 1; base[lab_obs] += 1; hit += int(fc["reaction"] == lab_obs); (early if n <= len(seq) // 2 else late).append(r["surprise"])
mj = base.most_common(1)[0]
print("tpj_backtest pairs=%d acc=%.3f majority_baseline=%.3f surprise_first_half=%.3f second_half=%.3f dist=%s" % (n, hit / max(1, n), mj[1] / max(1, n), sum(early) / max(1, len(early)), sum(late) / max(1, len(late)), dict(base)))
