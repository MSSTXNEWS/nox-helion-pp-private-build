#!/bin/bash
date -u +%T; cat /root/nox/logs/flash_ab.log; echo ==; grep -E "error|unknown|invalid|print_timing|eval time" /root/nox/logs/glm_8081.log | tail -6 | cut -c1-180
cat /proc/loadavg; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader; pgrep -af 'port 8081' | cut -c1-80
