#!/bin/bash
python3 - <<'PY'
import json,os
p="/root/nox/state/c602_verify.json"
print("done" if os.path.exists(p+".done") else "running")
for i,r in enumerate(json.load(open(p))):
    print(i+1,r["q"][:28],"|",r["tier"],r["len"],"s%d"%r["sent"],"%ss"%r["s"],"I" if r["intro"] else "","TY" if r["ty"] else "","EMPTY" if r["empty"] else "","|",r["a"][:200].replace("\n"," "))
PY
