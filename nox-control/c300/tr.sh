#!/bin/bash
f=$(ls -t /root/nox/state/core_trace/*.json | head -1); echo $f
python3 - "$f" <<'P'
import json,sys
d=json.load(open(sys.argv[1]))
def walk(x,pre=""):
    if isinstance(x,dict):
        for k,v in x.items():
            if isinstance(v,(dict,list)): walk(v,pre+k+".")
            elif any(s in k for s in ("ms","sec","dur","time","tier","path","organ","step","name","status","err","why")): print(pre+k,"=",str(v)[:100])
    elif isinstance(x,list):
        for i,v in enumerate(x[:40]): walk(v,pre+str(i)+".")
walk(d)
P
