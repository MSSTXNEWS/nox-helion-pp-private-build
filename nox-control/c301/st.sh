#!/bin/bash
echo "health:"; curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/health; curl -s -m 5 http://127.0.0.1:8081/health | head -c 200; echo
ps -eo pid,etimes,pcpu,rss,args | grep -E "llama-server|flash.py" | grep -v grep | cut -c1-330
echo "--- flash.log"; tail -8 /root/nox/logs/flash.log | cut -c1-220
echo "--- flash.out"; tail -8 /root/nox/logs/flash.out | cut -c1-220
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
free -g | sed -n 2p; ls /dev/shm/glm53f | head; ls -d /root/nox/dl/v7/*/ 2>/dev/null | head -30; ls /root/nox/*.py | head -40
