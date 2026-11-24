#!/bin/bash
PY=/workspace/nox/venv/bin/python; S=/workspace/nox/web/site
( $PY -m playwright install chromium-headless-shell > /workspace/nox/agent/out/c300_pw.log 2>&1; timeout 280 $PY /tmp/bt.py > /workspace/nox/agent/out/c300_bt.log 2>&1 ) &
python3 - <<'P'
import json
d=json.load(open("/workspace/nox/web/site/nav.json"))
def sh(o,dep=0):
    if isinstance(o,dict):
        print("  "*dep+"{"+", ".join("%s=%s"%(k,(str(v)[:28] if not isinstance(v,(list,dict)) else type(v).__name__+str(len(v)))) for k,v in o.items())+"}")
        for v in o.values():
            if isinstance(v,(list,dict)) and dep<2: sh(v,dep+1)
    elif isinstance(o,list):
        for x in o[:4]: sh(x,dep)
        if len(o)>4: print("  "*dep+"... +%d"%(len(o)-4))
sh(d)
P
grep -n "nav.json\|dock\b\|class=\"dock\|'dock'\|bottom" $S/nox-shell.js | head -12 | cut -c1-200
