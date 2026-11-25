#!/bin/bash
# P2 read-only: who uses LLM ports 8104 8106 8141 8142 8143 8151 8152 8811 8812
for p in 8104 8106 8141 8142 8143 8151 8152 8811 8812; do
  echo "=== PORT $p"
  echo "established_now: $(ss -tnH state established "( dport = :$p or sport = :$p )" 2>/dev/null | wc -l)"
  ss -tnpH state established "( dport = :$p )" 2>/dev/null | awk '{print $5}' | wc -l >/dev/null
  # client processes
  ss -tnpH state established "( dport = :$p )" 2>/dev/null | grep -o 'users:(("[^"]*",pid=[0-9]*' | sort | uniq -c | head -8
  echo "config refs (files mentioning :$p, excluding logs):"
  grep -rIl --include='*.py' --include='*.yaml' --include='*.yml' --include='*.json' --include='*.sh' --include='*.env' --include='*.toml' -E "[:=\"' ]$p([^0-9]|\$)" /workspace/nox/serve /workspace/nox/router /workspace/nox/judges /workspace/nox/stewards /workspace/nox/agent /workspace/nox/ops /workspace/nox/brain /workspace/nox/svc /workspace/nox/distill_v2 /workspace/nox/cascade 2>/dev/null | head -12
done
echo "=== LISTENERS 8400/8300/8200 cmd"
for p in 8400 8300 8200; do pid=$(ss -ltnpH "sport = :$p" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "$p pid=$pid cwd=$(readlink /proc/$pid/cwd)"; tr '\0' ' ' </proc/$pid/cmdline | cut -c1-200; echo; done
echo "=== llama-swap.yaml"; sed -n 1,80p /workspace/nox/serve/llama-swap.yaml 2>/dev/null | cut -c1-180
echo "=== logs last-hour activity"
find /workspace/nox -xdev -maxdepth 4 -name '*.log' -mmin -60 2>/dev/null | grep -Ei '8104|8106|8141|8142|8143|8151|8152|steward|advis|judge|cascade|llama' | head -20
echo "=== parent of 8141/8142/8143 (3343782) and 8151/8152 (58451)"
for pid in 3343782 58451; do echo "$pid: $(tr '\0' ' ' </proc/$pid/cmdline | cut -c1-200)"; done
echo "=== distill teacher refs"
grep -nE '81[0-9][0-9]|8104|8106|teacher' /workspace/nox/distill_v2.py /workspace/nox/distill_v2/*.py /workspace/nox/agent/autotrain/autotrain.sh 2>/dev/null | cut -c1-200 | head -20
echo "=== load: it/s of training"
tail -5 /workspace/nox/agent/autotrain/rounds/r028/train.log 2>/dev/null | cut -c1-200
echo "=== DONE"
