echo "C300: srv_k76"
N=/workspace/nox; cb=$(date +%s)
curl -s -m 30 "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$cb" -o /tmp/relaunch_k1.py
[ -e $N/state/ab_running.lock ] && { echo "A/B lock — стоп"; exit 1; }
echo "DPO/train процессы (не трогаем):"; pgrep -fa "train_dpo|chain4|distill_v2.py train" | cut -c1-80
L=$N/agent/out
echo "== pipeline"; P=$(pgrep -f "pipeline_svc.py" | head -1); $N/venv/bin/python -I /tmp/relaunch_k1.py $P $L/k1_restart.log http://127.0.0.1:18217/
echo "== judges"; P=$(pgrep -f "uvicorn judge_service" | head -1); $N/venv/bin/python -I /tmp/relaunch_k1.py $P $L/k1_restart.log http://127.0.0.1:8300/
echo "== core"; $N/venv/bin/python -I $N/state/liska_restart_core.py 2>&1 | tail -3; sleep 20; curl -s -m 5 -o /dev/null -w "core8090 %{http_code}\n" http://127.0.0.1:8090/
echo "== web"; P=$(pgrep -f "python web_server.py" | head -1); $N/venv/bin/python -I /tmp/relaunch_k1.py $P $L/k1_restart.log http://127.0.0.1:8091/
echo "== 8104 (фон)"; 
cat > /tmp/k1_donor.sh <<'D'
A=/workspace/nox/agent/autotrain; P=$(ss -ltnp | grep ':8104 ' | grep -oP 'pid=\K[0-9]+' | head -1); [ -n "$P" ] && kill $P
for i in $(seq 40); do [ -z "$(ss -ltnp | grep ':8104 ' | head -1)" ] && break; sleep 2; done
( set -a; . $A/donor.env 2>/dev/null; set +a; mapfile -t ARGS < $A/donor_hybrid.cmd; setsid nohup "${ARGS[@]}" > /workspace/nox/agent/out/donor_k1_restart.log 2>&1 9>&- & )
for i in $(seq 120); do curl -s -m2 localhost:8104/health | grep -q ok && { echo "$(date -u +%T) donor ok" >> /workspace/nox/agent/out/k1_restart.log; exit 0; }; sleep 4; done
echo "$(date -u +%T) donor НЕ поднялся" >> /workspace/nox/agent/out/k1_restart.log
D
setsid -f bash /tmp/k1_donor.sh </dev/null >/dev/null 2>&1
sleep 3; echo started
for p in 8091 8090 8300 8510 18217; do curl -s -m 5 -o /dev/null -w "$p %{http_code}\n" http://127.0.0.1:$p/; done
