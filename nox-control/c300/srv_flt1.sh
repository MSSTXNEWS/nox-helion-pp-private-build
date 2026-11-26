#!/bin/bash
D=/workspace/nox/distill_v2
python3 -I - <<'PY'
import json,collections
D="/workspace/nox/distill_v2"
for fn in ("rows_train.jsonl","raw.jsonl","items_base.jsonl"):
    try:
        n=0;ks=collections.Counter();src=collections.Counter()
        for l in open(D+"/"+fn,encoding="utf-8"):
            if not l.strip(): continue
            r=json.loads(l); n+=1
            if n==1: print(fn,"keys",list(r.keys()))
            for k in ("teacher","source","src","model","origin","license","lic","provider","dataset"):
                if k in r: src[(k,str(r[k])[:40])]+=1
        print(fn,n,src.most_common(25))
    except Exception as e: print(fn,"ERR",e)
PY
grep -n -i -E "claude|anthropic|license|licen|noncomm|nc-|cc-by-nc|forbid|blocklist|BAN" $D/code/distill_v2.py | cut -c1-190 | head -30
