echo "K1: ln_r4"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
curl -s -m5 -i 127.0.0.1:8091/api/nox/agenda | head -12 | cut -c1-200
curl -s -m5 -i 127.0.0.1:18091/api/nox/agenda | head -3
grep -n "owner_gate\|503" $N/web/pkg/server/web_server.py | head -20 | cut -c1-200
ls -la $N/state/owner_gate* | head; 
grep -rn "api/nox/agenda" $N/web/pkg/server/*.py | head -3 | cut -c1-200
