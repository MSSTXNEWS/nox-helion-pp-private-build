#!/bin/bash
cp -n /root/nox/start_glm.sh /root/nox/start_glm.sh.bak_np1
sed -i 's/--parallel 1 -c 16384/--parallel 4 -c 32768/' /root/nox/start_glm.sh
grep -c "parallel 4 -c 32768" /root/nox/start_glm.sh
nohup setsid bash /root/nox/start_glm.sh > /root/nox/logs/start_glm_p4.log 2>&1 < /dev/null &
for i in $(seq 1 60); do sleep 5; [ "$(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/health)" = 200 ] && break; done
echo up after $((i*5))s health=$(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/health)
ps -o args= -p $(pgrep -f "llama-server.*port 8081" | head -1) | cut -c1-400; nvidia-smi --query-gpu=memory.used --format=csv,noheader
grep -a -E "n_slots|n_ctx_slot" /root/nox/logs/glm_8081.log | head -2 | cut -c1-200
