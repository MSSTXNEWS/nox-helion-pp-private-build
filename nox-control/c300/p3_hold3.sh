N=/workspace/nox; n=$(grep -n "def chat_active" $N/stewards/nox_orch.py | cut -d: -f1); sed -n "$((n-25)),$((n+45))p" $N/stewards/nox_orch.py | cut -c1-230
echo "== recent turns in core log / conv files (who sends)"; ls -t $N/state/core/core_conv_*.json | head -5 | while read f; do echo "$(date -r $f +%T) $f $(python3 -c "
import json,sys
d=json.load(open('$f')); m=d.get('messages') or d.get('turns') or []; print(len(m), str(m[-1])[:140] if m else '')" 2>/dev/null)"; done
tail -n 5 $N/agent/out/core_8090.log | cut -c1-220
echo "== web access: who calls /api/chat /api/turn (recent web log)"; P=$(pgrep -f "python web_server.py"|head -1); tail -n 5 $(readlink /proc/$P/fd/1) 2>/dev/null | cut -c1-200
ss -Htnp state established '( dport = :8091 or dport = :8090 or dport = :8084 )' | grep -o 'users:(("[^"]*",pid=[0-9]*' | sort | uniq -c | head
