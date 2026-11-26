#!/bin/bash
python3 -I - <<'PY'
import json
r=json.load(open("/workspace/nox/distill_v2/gates/942c305f365080ac.json"))
f=r["failures"]; print(type(f).__name__, (list(f.keys()) if isinstance(f,dict) else len(f)))
def show(x,n=0):
    if isinstance(x,dict):
        for k,v in list(x.items())[:12]:
            if isinstance(v,(dict,list)) and n<2: print(" "*n+str(k)+":"); show(v,n+2)
            else: print(" "*n+str(k)+": "+str(v)[:230].replace("\n"," "))
    elif isinstance(x,list):
        for it in x[:6]: show(it,n+2); print(" "*n+"--")
show(f)
PY
