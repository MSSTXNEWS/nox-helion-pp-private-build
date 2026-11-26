#!/bin/bash
python3 -I - <<'PY'
import json
d=json.load(open("/workspace/nox/state/persona.json"))
print(list(d.keys()))
for k,v in d.items():
    s=json.dumps(v,ensure_ascii=False)
    if k!="living_engines": print(k,":",s[:420])
PY
echo == v5 curated
D=/workspace/nox/distill_v2
python3 -I - <<'PY'
import json,glob,collections
D="/workspace/nox/distill_v2"; C=collections.Counter(); ex={}
for f in glob.glob(D+"/raw_skill*v5_curated*.jsonl"):
    for l in open(f,encoding="utf-8"):
        r=json.loads(l); C[r.get("source")]+=1; ex.setdefault(r.get("source"),(r["prompt"][:150],r["answer"][:260]))
print(C)
for k,v in ex.items(): print(k,"|",v)
PY
