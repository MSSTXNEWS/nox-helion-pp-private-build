#!/bin/bash
date -u +%T; curl -s -m3 127.0.0.1:8081/health; echo; pgrep -af 'port 8081' | cut -c1-60; for p in $(pgrep -f 'port 8081'); do ps -o etimes=,args= -p $p | cut -c1-260; done
pgrep -af "glm_watch|start_glm|flash_ab|c4|c6|c320" | grep -v pgrep | cut -c1-150
tail -3 /root/nox/logs/glm_watch.log 2>/dev/null; nvidia-smi --query-gpu=memory.used --format=csv,noheader
