#!/bin/bash
date -u +%T; cat /root/nox/logs/flash_ab.log; grep -- "-ngl" /root/nox/start_glm.sh | grep -o "ngl [0-9]*"
cat /proc/loadavg; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
