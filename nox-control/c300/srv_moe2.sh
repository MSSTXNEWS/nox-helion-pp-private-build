#!/bin/bash
cat > /tmp/p3_dv2_moe_patch.py <<'PYEOF'
import sys,shutil,time,py_compile
F="/workspace/nox/distill_v2/code/distill_v2.py"; s=open(F,encoding="utf-8").read()
if "MOE_BACKEND_P3" in s: print("already"); sys.exit(0)
shutil.copy(F,F+".bak_moebe_%d"%int(time.time()))
a="import urllib.request\n"; assert s.count(a)==1
b=a+'''try:  # MOE_BACKEND_P3: A/B бэкенда MoE Unsloth через state/speed.json moe_backend (до импорта unsloth). Откат: убрать ключ.
    _mb = json.load(open("/workspace/nox/state/speed.json")).get("moe_backend")
    if _mb in ("grouped_mm", "unsloth_triton", "native_torch"): os.environ["UNSLOTH_MOE_BACKEND"] = _mb
except Exception: pass
'''
s=s.replace(a,b,1); open(F,"w",encoding="utf-8").write(s); py_compile.compile(F,doraise=True); print("patched")
PYEOF
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
SPEED = "/workspace/nox/state/speed.json"; ROUNDS = "/workspace/nox/agent/autotrain/rounds"
def moe_ab():  # MOE_AB_P3: A/B UNSLOTH_MOE_BACKEND; ранний откат, если раунд медленнее эталона >8% или упал без шагов
    sp = jl(SPEED, {}); be = sp.get("moe_backend")
    if not be: return
    ref = float(sp.get("_moe_ref_s") or 23.7); rounds = sorted(glob.glob(ROUNDS + "/r0*"), key=os.path.getmtime)
    if not rounds: return
    log = rounds[-1] + "/train.log"
    if not os.path.exists(log) or os.path.getmtime(log) < float(sp.get("_moe_set_ts") or 0): return   # раунд ещё старый
    txt = open(log, errors="replace").read()[-200000:]
    import re as _re
    m = _re.findall(r"скорость: ([0-9.]+) с/шаг", txt); alive = training(); verdict_ = None
    if m:
        v = float(m[0]); verdict_ = ("REVERT" if v > ref * 1.08 else "KEEP", v)
    elif not alive and ("Traceback" in txt or "Error" in txt): verdict_ = ("REVERT", None)
    elif alive and time.time() - os.path.getmtime(log) > 1500 and "шаг" not in txt: verdict_ = ("REVERT", None)
    if not verdict_: return
    open(OUT + "/moe_ab.log", "a").write("%s backend=%s ref=%.1f got=%s -> %s\n" % (time.strftime("%FT%TZ", time.gmtime()), be, ref, verdict_[1], verdict_[0]))
    sp["_moe_result"] = {"backend": be, "s_per_step": verdict_[1], "ref": ref, "verdict": verdict_[0]}
    if verdict_[0] == "REVERT":
        sp.pop("moe_backend", None)
        if alive: subprocess.run(["pkill", "-f", "distill_v2.py train"], capture_output=True)   # autotrain начнёт следующий раунд без ключа
    sp.pop("_moe_set_ts", None); json.dump(sp, open(SPEED, "w"), ensure_ascii=False, indent=1)
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
            moe_ab()
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
python3 -I /tmp/p3_dv2_moe_patch.py || exit 1
sed -n 12,22p $N/distill_v2/code/distill_v2.py | cut -c1-140
python3 -I - <<'PY'
import json,time
p="/workspace/nox/state/speed.json"; d=json.load(open(p))
d.update({"moe_backend":"unsloth_triton","_moe_ref_s":23.7,"_moe_set_ts":time.time(),"_moe_why":"SRV 26.11 A/B UNSLOTH_MOE_BACKEND grouped_mm(по умолчанию) -> unsloth_triton; ранний откат демоном p3_axis_guard если >8% медленнее или падение"})
json.dump(d,open(p,"w"),ensure_ascii=False,indent=1); print("speed.json set")
PY
kill $(cat $N/state/p3/axis_guard.pid) 2>/dev/null; sleep 1
setsid -f $N/venv/bin/python -I $N/ops/p3_axis_guard.py > $N/state/p3/axis_guard.out 2>&1 < /dev/null
sleep 3; pgrep -f ops/p3_axis_guard.py | head -1 > $N/state/p3/axis_guard.pid; sleep 20; cat $N/state/p3/axis_guard.err 2>/dev/null | tail -3; pgrep -f ops/p3_axis_guard.py
