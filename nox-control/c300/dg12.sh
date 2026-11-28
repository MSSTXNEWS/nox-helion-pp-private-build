echo "K1: dg12 (read-only)"; N=/workspace/nox; O=$N/ops
echo "report_for def:"; grep -nE "^def report_for|^def policy|crit|\"share\"|'share'|\"mb\"|\"fid\"|core|ядр" $O/liska_gates.py | cut -c1-170 | head -40
echo "--- latest relgates keys"; python3 - <<'PY'
import json,glob,os
f=sorted(glob.glob("/workspace/nox/distill_v2/gates/*.json"),key=os.path.getmtime)
print("gates files",len(f))
for p in f[-12:]:
    try: d=json.load(open(p))
    except Exception: continue
    if isinstance(d,dict) and ("soul" in d or "fid" in d):
        print(os.path.basename(p)[:30],"keys",list(d)[:10],"soul",{k:(v if isinstance(v,(int,float)) else type(v).__name__) for k,v in (d.get("soul") or {}).items()},"fid_keys",list((d.get("fid") or {}))[:6],"mb",{k:v for k,v in (d.get("mb") or {}).items() if isinstance(v,(int,float))})
        break
PY
echo END
