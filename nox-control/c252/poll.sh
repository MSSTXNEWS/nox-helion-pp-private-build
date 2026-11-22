#!/bin/bash
sleep 120; cat /root/nox/logs/B_bench_${1:-base}.out | cut -c1-900; cat /proc/loadavg; ps -o pcpu,etime -p $(pgrep -f 'ik_llama.*8081')|tail -1
curl -s -m 5 localhost:8081/health; echo; tail -c 600 /root/nox/logs/glm*.log 2>/dev/null | tail -5
