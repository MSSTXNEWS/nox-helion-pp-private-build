#!/bin/bash
N=/workspace/nox
echo "== chain tail"; sed -n '/AFTER-EXCL/,$p' $N/state/p3/chain_tune1.txt | head -24
echo "== slot task churn (every 4s x 10)"
for i in $(seq 1 10); do curl -s -m3 127.0.0.1:8104/slots | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(' | '.join('%s:%s n_dec=%s max=%s'%(s['id'],s['id_task'] if s['is_processing'] else '-',s.get('next_token',[{}])[0].get('n_decoded'),s.get('params',{}).get('max_tokens') or s.get('params',{}).get('n_predict')) for s in d))"; sleep 4; done
echo "== established conns with owner pid + age"
for sp in $(ss -Htn state established '( dport = :8104 )' | awk '{print $4}' | sed 's/.*://'); do o=$(ss -Htnp state established "( sport = :$sp )" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$o" ] && echo "port $sp pid $o $(tr '\0' ' ' </proc/$o/cmdline | cut -c1-90) age=$(ps -o etimes= -p $o)s"; done
echo "== nox_agents task threads using 8104 (py-spy absent) env/limits"; grep -n -E "max_tokens|slots|chat_busy|def donor_ok|free" $N/agent/nox_agents/lib.py | cut -c1-170 | sed -n 1,30p
echo "== agent_backends.json"; sed -E 's/("(key|token)[^"]*": *")[^"]*/\1***/Ig' $N/state/agent_backends.json | head -30
echo "== nox_core 8104 refs"; grep -n -E "8104|NOX_SEED|donor" $N/brain/BRAIN/nox_core.py | cut -c1-170 | head -12
echo "== chat priority file"; ls -la $N/state/orch/ 2>/dev/null | head; cat $N/state/chat_activity* 2>/dev/null | head -3
