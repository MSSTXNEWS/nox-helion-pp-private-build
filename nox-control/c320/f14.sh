#!/bin/bash
pkill -f flashopt.py; sleep 2; pkill -f 'llama-server.*--port 8081'; sleep 5
for p in $(pgrep -f embed_server.py); do kill -CONT $p 2>/dev/null; done
cd /root/nox/state/flash_bench; mkdir -p run1; mv *.srv.log *.cfg driver.log FLASH_OPT.json run1/ 2>/dev/null
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c320/flashopt2.py -o /root/nox/flashopt.py
python3 -m py_compile /root/nox/flashopt.py && echo compiled
# restore the base server first (driver reads its cmdline)
setsid nohup bash /root/nox/start_glm.sh >/root/nox/logs/start_glm_r.log 2>&1 < /dev/null &
for i in $(seq 120); do curl -sf localhost:8081/health >/dev/null && break; sleep 2; done; curl -s localhost:8081/health
setsid nohup python3 /root/nox/flashopt.py > /root/nox/state/flash_bench/driver.out 2>&1 < /dev/null &
sleep 3; pgrep -af flashopt.py | cut -c1-60
