cat > /tmp/s5_md.py <<'P'
import shutil,time,py_compile
f="/workspace/nox/qa_audit.py"; s=open(f).read()
if "S5MEDIAN" in s: print("OUT: already"); raise SystemExit
old='    res["wow"] = j.get("wow")'
assert old in s
new='''    # S5MEDIAN: медиана трёх прогонов vision
    def _parse(txt):
        d = {}
        mm0 = re.search(r"\\{.*\\}", txt, re.S)
        try: d = json.loads(mm0.group(0)) if mm0 else {}
        except Exception: d = {}
        if not d:
            for kk in ("wow", "A", "R", "U"):
                q = re.search(r'"%s"\\s*:\\s*([0-9.]+)' % kk, txt)
                if q: d[kk] = float(q.group(1))
            for kk in ("handmade", "neon", "overlap"): d[kk] = bool(re.search(r'"%s"\\s*:\\s*true' % kk, txt))
        return d
    runs = [j] if j else []
    for _ in range(2):
        try: runs.append(_parse(vision(shots["desk"], pr)))
        except Exception: pass
    runs = [r_ for r_ in runs if isinstance(r_.get("wow"), (int, float))]
    if len(runs) >= 2:
        import statistics
        for kk in ("wow", "A", "R", "U"):
            vals = [float(r_[kk]) for r_ in runs if isinstance(r_.get(kk), (int, float))]
            if vals: j[kk] = statistics.median(vals)
        for kk in ("handmade", "neon", "overlap"):
            j[kk] = sum(1 for r_ in runs if r_.get(kk)) * 2 > len(runs)
        j["toporno"] = j.get("toporno") if j.get("handmade") else []
        res["vision_runs"] = [[r_.get(k_) for k_ in ("wow", "A", "R", "U")] for r_ in runs]
'''
s=s.replace(old,new+old,1)
shutil.copy(f,f+".bak_s5_"+time.strftime("%H%M"))
open(f,"w").write(s); py_compile.compile(f,doraise=True); print("OUT: patched median")
P
/workspace/nox/venv/bin/python /tmp/s5_md.py 2>&1 | tail -3
