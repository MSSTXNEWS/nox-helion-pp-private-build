#!/bin/bash
date -u +%T; ps -eo pid,ppid,etimes,args | grep -E "llama-server|flash|glm_watch|watch" | grep -v grep | cut -c1-200
echo ---; tail -n 12 /root/nox/logs/flash_start.log | cut -c1-200
echo ---; grep -a -E "slot|error|killed|abort|OOM" /root/nox/logs/glm_8081.log | tail -n 12 | cut -c1-200
dmesg 2>/dev/null | tail -n 5 | cut -c1-160
free -g | sed -n 2p; cat /root/nox/logs/bench_speed.log | tail -n 6 | cut -c1-200
