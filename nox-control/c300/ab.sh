#!/bin/bash
date -u +%T; cat /root/nox/logs/flash_ab.log; echo ==; tr '\0' ' ' < /proc/$(pgrep -f 'llama.cpp-f.*8081' | head -1)/cmdline | cut -c60-400; echo
grep -E "error|invalid|unknown|print_timing|offload" /root/nox/logs/glm_8081.log | tail -8 | cut -c1-180; cat /proc/loadavg; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
