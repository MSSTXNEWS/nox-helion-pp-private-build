echo "C300: srv_k84"
date -u +%T
curl -s -m5 -w " code=%{http_code}\n" localhost:8104/health | head -c 200
tail -n 4 /workspace/nox/agent/out/k1_restart.log
pgrep -fa "port 8104" | cut -c1-100 | head -2
tail -n 3 /workspace/nox/agent/out/donor_k1_restart.log | cut -c1-200
cat /workspace/nox/agent/autotrain/mode
free -g | sed -n 2p; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
