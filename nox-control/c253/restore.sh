#!/bin/bash
pgrep -f 'llama-server.*--port 8081' >/dev/null && { echo "GLM уже жив"; } || {
 nohup setsid bash /root/nox/start_glm.sh > /root/nox/logs/B_restore.out 2>&1 &
 sleep 5; }
pgrep -f glm_watch.sh >/dev/null || { nohup setsid /root/nox/glm_watch.sh >/dev/null 2>&1 & }
sleep 20; ps -eo pid,etime,args | grep -E 'llama-server|glm_watch|exp_driver|start_glm|glm_tune|ab_bench' | grep -v grep | cut -c1-200
tail -5 /root/nox/logs/glm_watch.log; tail -3 /root/nox/logs/gateway.log | cut -c1-250
