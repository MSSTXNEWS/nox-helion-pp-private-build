#!/bin/bash
cat /workspace/nox/state/p3/persona_gen.json; echo; cat /workspace/nox/state/p3/persona_gen2.json 2>/dev/null; echo
tail -3 /workspace/nox/state/p3/persona_gen2.out | cut -c1-200
ls -la /workspace/nox/distill_v2/ | grep -E "p3_persona|p3_antisyc" | cut -c30-140
python3 -I - <<'PY'
import json,glob,collections
D="/workspace/nox/distill_v2"; C=collections.Counter(); ex={}
for f in glob.glob(D+"/raw_skill*p3_persona*.jsonl")+glob.glob(D+"/raw_skill*p3_antisyc_ru*.jsonl"):
    for l in open(f,encoding="utf-8"):
        r=json.loads(l); C[r["cat"]]+=1; ex.setdefault(r["cat"],(r["prompt"][:110],r["answer"][:230].replace("\n"," ")))
print(C)
for k,v in ex.items(): print(k,"|",v)
PY
