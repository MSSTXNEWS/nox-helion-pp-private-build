#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c320/flashopt3.py -o /root/nox/flashopt.py
python3 -m py_compile /root/nox/flashopt.py && echo compiled
for p in $(pgrep -f embed_server.py); do kill -CONT $p 2>/dev/null; done
curl -sf localhost:8081/health || { setsid nohup bash /root/nox/start_glm.sh >/root/nox/logs/start_glm_r.log 2>&1 < /dev/null & for i in $(seq 120); do curl -sf localhost:8081/health >/dev/null && break; sleep 2; done; }
curl -s localhost:8081/health; echo
cd /root/nox/state/flash_bench; mkdir -p run2; mv *.srv.log *.cfg driver.log FLASH_OPT.json run2/ 2>/dev/null
setsid nohup python3 /root/nox/flashopt.py > /root/nox/state/flash_bench/driver.out 2>&1 < /dev/null &
sleep 5; ps -eo pid,args | grep '[f]lashopt.py' | cut -c1-60; tail -n 3 driver.out
