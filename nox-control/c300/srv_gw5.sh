#!/bin/bash
curl -s -m5 127.0.0.1:8793/v1/chat_metric; echo
python3 -I - <<'PY'
import json,glob,collections
C=collections.Counter(); P=collections.Counter(); L=collections.defaultdict(list)
for f in glob.glob("/workspace/nox/state/gw_journal/*.jsonl"):
    for l in open(f):
        r=json.loads(l); C[(r["code"],r["prio"]>=9)]+=1; P[r["provider"]]+=1
        if r.get("ms"): L[r["provider"]].append(r["ms"])
print(sorted(C.items())); print(P.most_common(8))
for p,v in L.items():
    v.sort(); print(p,len(v),"p50",v[len(v)//2],"p90",v[int(len(v)*.9)])
PY
sed -n '/^router_settings/,$p;/^litellm_settings/,/^[a-z_]*:/p' /workspace/nox/router/config.yaml | head -40
python3 - <<'PY'
import json
d=json.load(open("/workspace/nox/state/advisors_external.json")); a=d.get("advisors",[])
import collections; print(len(a), collections.Counter((x.get("provider"),x.get("status")) for x in a).most_common(10))
PY
ls /workspace/nox/venv/bin/python; /workspace/nox/venv/bin/python -c "import litellm;print(litellm.__version__ if hasattr(litellm,'__version__') else 'ok')" 2>&1 | tail -1
