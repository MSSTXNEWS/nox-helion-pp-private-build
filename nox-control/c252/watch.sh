#!/bin/bash
ps -eo pid,etime,args | grep -E 'glm_watch|glm_tune|tuner|ab_bench|gateway|watch' | grep -v grep | cut -c1-200
crontab -l 2>/dev/null | grep -i glm | cut -c1-200
ls /root/nox/scripts 2>/dev/null | grep -iE 'glm|watch' | head
grep -n 'ngl\|base' /root/nox/dl/v7/exec2/nox_wow/SPD/matrix.json | head -5 | cut -c1-400
sed -n 299,320p /root/nox/dl/v7/exec2/nox_wow/SPD/ab_bench.py | cut -c1-160
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
