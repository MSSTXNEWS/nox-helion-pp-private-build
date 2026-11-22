#!/bin/bash
pgrep -f 'llama-server.*--port 8081' >/dev/null && { echo already_up; exit 0; }
cp -a /root/nox/start_glm.sh /root/nox/backup/start_glm.sh.$(date +%H%M%S)
setsid nohup bash /root/nox/start_glm.sh >/root/nox/logs/start_glm_restore.log 2>&1 < /dev/null &
for i in $(seq 100); do curl -sf localhost:8081/health >/dev/null && break; sleep 2; done
curl -s localhost:8081/health; echo; pgrep -af 'llama-server.*8081' | cut -c1-100; tail -n 3 /root/nox/logs/start_glm_restore.log | cut -c1-200
grep -n -iE 'pkill|killall|kill ' /root/nox/*.sh 2>/dev/null | grep -i llama | cut -c1-140 | head -8
