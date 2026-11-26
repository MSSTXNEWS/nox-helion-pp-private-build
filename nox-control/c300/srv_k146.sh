echo "C300: srv_k146"
cd /workspace/nox; date -u +%T
ss -ltnp 2>/dev/null | grep ":8084 " | awk '{print $4,$6}' | cut -c1-80
for p in $(pgrep -f "distill_v2.py train") $(pgrep -f "Qwen3-30B-A3B-Instruct-2507") $(pgrep -f "port 8141") $(pgrep -f "port 8144") $(pgrep -f "port 8811") $(pgrep -f "tensorboard_data_server"); do echo "pid $p nice было $(ps -o ni= -p $p)"; renice -n 12 -p $p >/dev/null 2>&1; done
for p in $(pgrep -f "port 8104") $(pgrep -f "port 8084"); do echo "чат pid $p nice $(ps -o ni= -p $p)"; done
sleep 5; uptime | sed 's/.*load/load/'
timeout 150 python3 /tmp/k1probe.py 8091 2>&1 | head -4 | cut -c1-700
