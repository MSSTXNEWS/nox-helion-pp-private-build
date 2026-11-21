#!/bin/bash
# повторный замер (тёплый кеш) + диагностика: major faults, загрузка CPU, NUMA
P=$(pgrep -f "llama-server -m" | head -1); echo "pid $P"; grep -E "ctxt|^Cpus_allowed_list" /proc/$P/status | head -2
cat /sys/fs/cgroup/cpu.max 2>/dev/null; nproc; taskset -p $P
echo "majflt before:"; awk '{print $12}' /proc/$P/stat
for i in 1 2; do curl -s http://127.0.0.1:8081/completion -d '{"prompt":"Расскажи коротко о Python.","n_predict":100,"cache_prompt":false}' | python3 -c "
import sys,json; t=json.load(sys.stdin)['timings']; print('prompt %.1f t/s | gen %.2f t/s'%(t['prompt_per_second'],t['predicted_per_second']))"; done
echo "majflt after:"; awk '{print $12}' /proc/$P/stat
top -bn1 -p $P | tail -2 | cut -c1-120; numactl -H 2>/dev/null | head -4; lscpu | grep -E "NUMA node[0-9]"
