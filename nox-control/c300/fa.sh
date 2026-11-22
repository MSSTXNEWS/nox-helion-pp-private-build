#!/bin/bash
tr '\0' ' ' < /proc/$(pgrep -f 'llama.cpp-f.*8081' | head -1)/cmdline | cut -c1-600; echo
grep -E "offloaded|buffer size|n_ctx|KV|not supported|fallback|CPU_REPACK|kda|KDA|warn" /root/nox/logs/glm_8081.log | head -30 | cut -c1-200
cat /proc/loadavg; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
