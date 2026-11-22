#!/bin/bash
date -u +%T; echo health=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health)
tail -n 3 /root/nox/logs/flash.log | cut -c1-150; ls -l /dev/shm/glm53f/*00005* | cut -c20-90
ps -eo pid,etimes,args | grep -E "flash.py|llama-server" | grep -v grep | cut -c1-120
for f in /root/nox/logs/bench_*.log /root/nox/logs/glm_8081.log; do echo "== $f"; tail -n 8 $f 2>/dev/null | cut -c1-220; done
cat /root/nox/state/FLASH_SPEED.json 2>/dev/null | head -c 1200
nvidia-smi --query-gpu=memory.used --format=csv,noheader
