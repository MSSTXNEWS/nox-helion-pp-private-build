#!/bin/bash
pkill -f flash_ab2.sh; pkill -f flash_ab.sh
grep -iE "out of memory|cudaMalloc|failed to allocate|error" /root/nox/logs/glm_8081.log | head -4 | cut -c1-200
cp /root/nox/start_glm.sh.ngl24 /root/nox/start_glm.sh
nohup setsid bash /root/nox/flash_ab.sh >/dev/null 2>&1 < /dev/null &
cat /root/nox/glm_watch.sh | head -12
