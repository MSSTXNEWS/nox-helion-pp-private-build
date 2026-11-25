NOX=/workspace/nox
echo "hold: $(cat $NOX/state/orch/chat_hold)"; tail -8 $NOX/state/orch/guard.log | cut -c1-250
python3 -c "
import json;d=json.load(open('$NOX/state/arbiter.json'));print({k:d[k] for k in d if k!='procs'})"
for i in 1 2 3 4 5 6 7 8; do echo "$(date +%T) hold_age=$(( $(date +%s) - $(stat -c %Y $NOX/state/orch/chat_hold) )) core=$(curl -s -m3 127.0.0.1:8090/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("running"),d.get("glm"))')"; sleep 5; done
head -40 $NOX/stewards/chat_guard.py 2>/dev/null | cut -c1-200
ls -la --time-style=full-iso $NOX/state/orch/guard.log
