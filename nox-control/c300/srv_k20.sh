echo "C300: srv_k20"
cd /workspace/nox
G=distill_v2/gates; ls -la $G | head -3; ls $G | wc -l
F=$G/426f90c1ed069091-eval-*.json; python3 - $F <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(type(d).__name__, list(d)[:20] if isinstance(d,dict) else len(d))
def show(x,dep=0):
    if dep>3: return
    if isinstance(x,dict):
        for k,v in list(x.items())[:12]:
            print(' '*dep+str(k), type(v).__name__, (str(v)[:120] if not isinstance(v,(dict,list)) else len(v)))
            if isinstance(v,(dict,list)) and dep<2: show(v if isinstance(v,dict) else (v[0] if v else {}),dep+1)
show(d)
PY
echo == antisyc; head -c 700 state/p3/antisyc_injected.json; echo; wc -l distill_v2/raw_skill_p3_antisyc_001.jsonl; head -c 900 distill_v2/raw_skill_p3_antisyc_001.jsonl; echo
ls distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724 | head; du -sh distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724
grep -n "resume\|--init\|adapter\|--ckpt\|add_argument" distill_v2/code/distill_v2.py | sed -n '1,60p' | cut -c1-170
ls -la brain/SLP | head -20
