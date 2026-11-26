#!/bin/bash
echo "load: $(cat /proc/loadavg)"
ps -eo pid,ni,pcpu,psr,args --sort=-pcpu | head -16 | cut -c1-120
for p in $(pgrep -f 'judge_service|embed_server|nox_core.py|distill_v2|cascade|llama-server' ); do echo "$p ni=$(ps -o ni= -p $p) $(grep Cpus_allowed_list /proc/$p/status | cut -f2) thr=$(ls /proc/$p/task | wc -l) $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-60)"; done
cat /workspace/nox/state/p3/ledger.jsonl | tail -5 | cut -c1-250
grep -n -i -E "cpuset|taskset" /workspace/nox/stewards/*.py 2>/dev/null | head -8 | cut -c1-170
