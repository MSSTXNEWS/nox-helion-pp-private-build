cd /workspace/nox/web/pkg/server
timeout 60 /workspace/nox/venv/bin/python - <<'P'
import sys,time; sys.path.insert(0,'.')
import chat_core as CC
t=CC.Turn('unit-test','x'); t.register(); t.last=time.time()-999; t.t0=t.last
print('UNIT running_before', CC.running_turn('unit-test') is not None, 'ACTIVE', len(CC.ACTIVE))
P
./run_web.sh restart 2>&1 | tail -3; sleep 6
curl -s -m 8 -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8091/api/chat/health
echo ==CORE; curl -s -m 8 http://127.0.0.1:8090/health | grep -o '"running": [0-9]*\|"turns": [0-9]*'
for ep in /v1/stop; do curl -s -m 8 -X POST -H 'Content-Type: application/json' -d '{"all":true}' http://127.0.0.1:8090$ep | head -c 300; echo; done
sleep 2; curl -s -m 8 http://127.0.0.1:8090/health | grep -o '"running": [0-9]*'
curl -s -m 8 http://127.0.0.1:8090/ | head -c 300; echo
curl -s -m 8 -X POST -H 'Content-Type: application/json' -d '{"all":true}' http://127.0.0.1:8091/api/turn/stop; echo
