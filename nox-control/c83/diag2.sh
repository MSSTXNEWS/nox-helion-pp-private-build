#!/bin/bash
# c83: read-only: почему dispatcher не берёт pending (owner_order/track)
for p in nox-priority-scheduler nox-dispatcher-t855u nox-priority-arbiter; do echo "== $p"; supervisorctl tail -3000 $p 2>/dev/null | tail -n 7 | cut -c1-230; done
echo "== state gating"; python3 - <<'P'
import json,os,time
d='/root/nox/state/dispatcher/'
for f in os.listdir(d):
    if f.endswith('.json') and os.path.getsize(d+f)<200000 and any(k in f for k in ('sched','prior','gate','lease','claim','owner','stop')):
        try: print(f, json.dumps(json.load(open(d+f)),ensure_ascii=False)[:260])
        except Exception as e: print(f,'err',e)
s=json.load(open(d+'state.json')); print({k:(v if not isinstance(v,(dict,list)) else type(v).__name__+str(len(v))) for k,v in list(s.items())[:14]})
P
ls /root/nox/state | grep -iE "stop|owner|hold|pause" | head -8
