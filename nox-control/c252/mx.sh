#!/bin/bash
cd /root/nox/dl/v7/exec2/nox_wow/SPD
python3 - <<'PY'
import json
m=json.load(open('matrix.json'))
print(list(m.keys()) if isinstance(m,dict) else type(m))
for k,v in m.items():
    if k in('levers','rычаги') or isinstance(v,list):
        for x in v: print(json.dumps(x,ensure_ascii=False)[:230])
    else: print(k, json.dumps(v,ensure_ascii=False)[:300])
PY
