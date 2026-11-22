#!/bin/bash
ps -eo pid,etimes,ni,pcpu,args | grep -E 'flash_ab|flash_try|tune_worker|glm_watch|flash_start' | grep -v grep | cut -c1-120
tail -n 4 /root/nox/logs/flash_ab*.log 2>/dev/null | cut -c1-160 | tail -8; ls -la --time-style=+%H:%M /root/nox/logs/flash_ab*.log | awk '{print $6,$7}'; date +%H:%M
