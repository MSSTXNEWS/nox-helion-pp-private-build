#!/bin/bash
F=/workspace/nox/ops/liska_gates.py
grep -n "^POLICY" -A14 $F | cut -c1-200
grep -n -E "round_gates|promot|cand" /workspace/nox/distill_v2/code/distill_v2.py | grep -v -E "^.*#" | cut -c1-170 | head -20
grep -n -E "cand|promot" /workspace/nox/agent/ckpt_guard.py | cut -c1-170 | head -20
python3 -I - <<'PY'
import json,glob,os
D="/workspace/nox/distill_v2/gates"
for f in sorted(glob.glob(D+"/decision_*.json"),key=os.path.getmtime)[-6:]:
    d=json.load(open(f)); print(os.path.basename(f)[:30],d["pass"],d["t"],[r[:70] for r in d["reasons"]][:3])
f=sorted((x for x in glob.glob(D+"/*.json") if "decision" not in x and "-eval-" not in x),key=os.path.getmtime)[-1]
r=json.load(open(f)); print(os.path.basename(f), list(r.keys())); print({k:(r[k].get("overall") if k=="mb" else r[k].get("score",r[k].get("share"))) for k in ("fid","soul","mb") if k in r})
PY
