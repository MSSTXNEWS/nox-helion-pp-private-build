#!/bin/bash
D=/workspace/nox/distill_v2
python3 - <<'PY'
import json,glob,os
D="/workspace/nox/distill_v2"
def sk(o,d=0):
    if isinstance(o,dict): return {k:sk(v,d+1) if d<2 else type(v).__name__ for k,v in list(o.items())[:14]}
    if isinstance(o,list): return "list[%d]"%len(o)
    return o if not isinstance(o,str) else o[:40]
fs=sorted(glob.glob(D+"/gates/*.json"),key=os.path.getmtime)
print(len(fs)); 
for f in fs[-2:]: print(os.path.basename(f)[:40], json.dumps(sk(json.load(open(f))),ensure_ascii=False)[:900])
print(json.dumps(sk(json.load(open(D+"/eval.json"))),ensure_ascii=False)[:700])
PY
ls -lt $D/ckpt_keep $D/ckpt_archive | head -20; cat /workspace/nox/agent/out/ckpt_guard.json | head -c 500
grep -n -i -E "def .*gate|gates/" $D/code/distill_v2.py | head -20 | cut -c1-200
ls /workspace/nox/agent/*gate* /workspace/nox/ops/*gate* 2>/dev/null
