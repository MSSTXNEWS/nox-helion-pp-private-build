#!/bin/bash
L=/workspace/nox/agent/out/nox_agents.log; B=$(wc -l < $L)
setsid -f bash /workspace/nox/agent/nox_agents/run_supervisor.sh restart > /tmp/rs.out 2>&1 < /dev/null
sleep 40; cat /tmp/rs.out; pgrep -af "nox_agents/supervisor.py" | cut -c1-90
echo "new errors since restart: $(tail -n +$B $L | grep -a -c -E 'Traceback|FileNotFound')"
curl -s -m5 127.0.0.1:8810/health | head -c 300; echo
curl -s -m8 127.0.0.1:8810/board | python3 -c "
import sys,json
d=json.load(sys.stdin); s=json.dumps(d,ensure_ascii=False); print(len(s)); print('ch-golden' in s, s[:500])"
ls -la /workspace/nox/state/agents/status.json; python3 -c "
import json;d=json.load(open('/workspace/nox/state/agents/status.json'));print(list(d.keys())[:8]); a=d.get('agents') or d; print([k for k in (a if isinstance(a,dict) else [x.get('name') for x in a])][:12])"
