#!/bin/bash
date -u +%T; cat /root/nox/flash_ab.sh | cut -c1-400 | head -40
echo ---; ps -o args= -p $(pgrep -f "port 8081" | head -1) | cut -c1-500
echo health=$(curl -s -m 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health); nvidia-smi --query-gpu=memory.used --format=csv,noheader
ls /root/nox/logs | tail -n 8; ls -t /root/nox/logs | head -n 5
