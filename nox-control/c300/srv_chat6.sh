#!/bin/bash
N=/workspace/nox
for i in 1 2 3; do curl -s -m3 127.0.0.1:8104/slots | python3 -c "
import sys,json
for s in json.load(sys.stdin):
    p=s.get('params',{}); print(s['id'],s['is_processing'],'dec',s.get('next_token',[{}])[0].get('n_decoded'),'max',p.get('n_predict'),p.get('max_tokens'))"; echo --; sleep 5; done
for sp in $(ss -Htn state established '( dport = :8104 )' | awk '{print $4}' | sed 's/.*://'); do o=$(ss -Htnp state established "( sport = :$sp )" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$o" ] && echo "pid $o $(tr '\0' ' ' </proc/$o/cmdline | cut -c1-100) age=$(ps -o etimes= -p $o)s"; done
echo == procs; ps -eo pid,etimes,pcpu,args --sort=-pcpu | grep -E 'python|node' | grep -v grep | head -25 | cut -c1-150
echo == slot reserve refs; grep -rn -E "reserve|slot_id|id_slot" $N/agent/nox_agents/lib.py $N/brain/BRAIN/pipeline*.py 2>/dev/null | head -10 | cut -c1-170
ls $N/state/orch; cat $N/state/orch/*.json 2>/dev/null | head -c 600
