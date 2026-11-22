#!/bin/bash
for i in $(seq 1 54); do c=$(curl -s -m 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health); [ "$c" = 200 ] && break; ! pgrep -f "python3 flash.py" >/dev/null && [ "$i" -gt 2 ] && pgrep -f "port 8081" >/dev/null || true; sleep 10; done
date -u +%T; echo health=$c; ps -eo pid,etimes,args | grep -E "flash.py|port 8081" | grep -v grep | cut -c1-260
tail -n 4 /root/nox/logs/flash.log | cut -c1-150; ls -ls /dev/shm/glm53f/*00005* | cut -c1-90
tail -n 5 /root/nox/logs/glm_8081.log | cut -c1-200; nvidia-smi --query-gpu=memory.used --format=csv,noheader
