#!/bin/bash
cat > /workspace/nox/ops/p3_axis_guard.py <<'PYEOF'
#!/usr/bin/env python3
# P3 axis guard (26.11): автооткат обучения. 1) считает падение осей кандидата против базы по отчётам ворот (порог 2 п.п.),
# 2) пока обучение не идёт, держит принятый лучший чекпойнт самым свежим в ckpt_keep (autotrain берёт `ls -td | head -1` как init-adapter),
# значит отклонённый/просевший кандидат не становится стартом следующего раунда, 3) пишет честный вердикт NO_GAIN.
import json, glob, os, time, subprocess
D = "/workspace/nox/distill_v2"; GD = D + "/gates"; KEEP = D + "/ckpt_keep"; GJ = "/workspace/nox/agent/out/ckpt_best_global.json"
OUT = "/workspace/nox/state/p3"; LOGF = OUT + "/axis_rollback.jsonl"; VERD = OUT + "/train_verdict.json"; DROP = 0.02
def jl(p, d=None):
    try: return json.load(open(p))
    except Exception: return d
def axes(r):
    a = {}
    f = r.get("fid") or {}
    if f.get("score") is not None: a["fid"] = f["score"]
    for k, v in (f.get("by_cat") or {}).items():
        if isinstance(v, (int, float)): a["fid:" + k] = v
    s = r.get("soul") or {}
    if s.get("share") is not None: a["soul"] = s["share"]
    o = (r.get("mb") or {}).get("overall")
    if o is not None: a["mb"] = o
    return a
def report_by_dir(d):
    best = None
    for f in glob.glob(GD + "/*.json"):
        if "decision" in f or "-eval-" in f: continue
        r = jl(f)
        if r and r.get("dir") == d and (best is None or os.path.getmtime(f) > best[0]): best = (os.path.getmtime(f), r)
    return best[1] if best else None
def check(decfile, seen):
    d = jl(decfile)
    if not d: return
    cs = d.get("cand_sha16"); cr = jl("%s/%s.json" % (GD, cs)); br = report_by_dir(d.get("base"))
    rec = {"t": time.strftime("%FT%TZ", time.gmtime()), "cand": d.get("cand"), "cand_sha16": cs, "gate_pass": d.get("pass")}
    if cr and br:
        ca, ba = axes(cr), axes(br)
        drops = {k: round(ba[k] - ca[k], 4) for k in ca if k in ba and ba[k] - ca[k] > DROP}
        rec["axes_dropped_over_2pp"] = drops
        rec["verdict"] = "ROLLBACK" if (drops or not d.get("pass")) else "ACCEPT"
    else:
        rec["verdict"] = "ROLLBACK" if not d.get("pass") else "ACCEPT"; rec["note"] = "нет отчёта базы/кандидата"
    open(LOGF, "a").write(json.dumps(rec, ensure_ascii=False) + "\n"); seen.add(decfile)
def verdict():
    ds = sorted(glob.glob(GD + "/decision_*.json"), key=os.path.getmtime)[-5:]
    L = [jl(x) or {} for x in ds]; acc = sum(1 for x in L if x.get("pass"))
    g = jl(GJ, {})
    v = {"t": time.strftime("%FT%TZ", time.gmtime()), "last_gates": len(L), "accepted": acc, "best_dir": g.get("dir"),
         "verdict": "NO_GAIN" if L and acc == 0 else ("GAIN" if L and L[-1].get("pass") else "MIXED"),
         "note": "NO_GAIN: ни один из последних кандидатов не прошёл ворота; обучение стартует с принятого лучшего" if L and acc == 0 else ""}
    json.dump(v, open(VERD, "w"), ensure_ascii=False, indent=1)
TR_CORES = {0, 1, 2, 3, 16, 17, 18, 19}; SPARE = "8-15,24-31"
KEEP = ("ckpt_guard", "distill_v2", "chat_guard")
def repin():  # REPIN_P3: убрать конкурентов с ядер тренера (nice 19 уступает всем на общих ядрах)
    try:
        import psutil
    except Exception: return 0
    n = 0
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
            if any(k in cl for k in KEEP) or p.pid == os.getpid(): continue
            aff = set(p.cpu_affinity())
            if not (aff & TR_CORES): continue
            if p.cpu_percent(interval=0.2) < 4: continue
            subprocess.run(["taskset", "-a", "-cp", SPARE, str(p.pid)], capture_output=True); n += 1
            open(OUT + "/repin.log", "a").write("%s pin %d %s\n" % (time.strftime("%T"), p.pid, cl[:80]))
        except Exception: pass
    return n
def training():
    return subprocess.run(["pgrep", "-f", "distill_v2.py train"], capture_output=True).returncode == 0
def main():
    os.makedirs(OUT, exist_ok=True)
    seen = set()
    done = set(json.loads(l).get('cand_sha16') for l in open(LOGF)) if os.path.exists(LOGF) else set()
    last_touch = 0; last_pin = 0
    while True:
        try:
            for f in sorted(glob.glob(GD + "/decision_*.json"), key=os.path.getmtime)[-3:]:
                s = (jl(f) or {}).get("cand_sha16")
                if s and s not in done: check(f, seen); done.add(s)
            verdict()
            if training() and time.time() - last_pin > 40: repin(); last_pin = time.time()
            g = jl(GJ, {}); b = g.get("dir")
            if b and os.path.isdir(b) and not training() and time.time() - last_touch > 25:
                os.utime(b, None); last_touch = time.time()
        except Exception as e:
            open(OUT + "/axis_guard.err", "a").write("%s %r\n" % (time.strftime("%T"), e))
        time.sleep(30)
if __name__ == "__main__": main()
PYEOF
N=/workspace/nox
cp -n $N/ops/p3_axis_guard.py $N/ops/p3_axis_guard.py.bak0 2>/dev/null
kill $(cat $N/state/p3/axis_guard.pid) 2>/dev/null; sleep 1
setsid -f $N/venv/bin/python -I $N/ops/p3_axis_guard.py > $N/state/p3/axis_guard.out 2>&1 < /dev/null
sleep 3; pgrep -f ops/p3_axis_guard.py | head -1 > $N/state/p3/axis_guard.pid
sleep 60; cat $N/state/p3/repin.log 2>/dev/null | tail -12; cat $N/state/p3/axis_guard.err 2>/dev/null | tail -2
T=$(pgrep -f "distill_v2.py train" | head -1)
top -H -b -n 2 -d 5 -p $T | awk '/^top/{c++} c==2 && NR>7' | head -4
L=$(ls -td $N/agent/autotrain/rounds/r0*/ | head -1)train.log; grep -a -E "скорость" $L | tail -3 | cut -c1-120
