#!/bin/bash
df -h /dev/shm | tail -1; ls -ls /dev/shm/glm53f; tail -5 /root/nox/logs/flash.log | cut -c1-200
tail -2 /root/nox/logs/flash_build.log | cut -c1-120
ps -eo pid,etimes,pcpu,args | grep -E "llama-server|flash.py|exp_driver|glm_watch|sr.sh" | grep -v grep | cut -c1-140
for p in /proc/[0-9]*; do grep -q 'gguf (deleted)' $p/maps 2>/dev/null && echo HOLD ${p#/proc/} $(tr '\0' ' ' <$p/cmdline|cut -c1-100); done
free -g | head -2
