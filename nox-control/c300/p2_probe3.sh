#!/bin/bash
# P2 read-only probe 3: CPU delta of LLM servers, train_cpu_pause, wave1 block A presence, ritual service :18215
echo "## CPU DELTA 45s"
for p in 8104 8106 8141 8142 8143 8151 8152 8811 8812; do pid=$(ss -ltnpH "sport = :$p" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$pid" ] && echo "$p $pid $(awk '{print $14+$15}' /proc/$pid/stat)"; done > /tmp/p2_a.txt
sleep 45
while read p pid t0; do t1=$(awk '{print $14+$15}' /proc/$pid/stat 2>/dev/null); echo "port $p cpu_ticks_delta=$((t1-t0)) (=$(( (t1-t0)/45 ))% of one core)"; done < /tmp/p2_a.txt
echo "## train_cpu_pause.sh"; sed -n 1,40p /workspace/nox/ops/train_cpu_pause.sh | cut -c1-200
echo "## cpu_judges start.sh"; sed -n 1,25p /workspace/nox/ops/cpu_judges_20261125/start.sh | cut -c1-200
echo "## 8106 keepers"; grep -nE '8106' /workspace/nox/stewards/judge_keep.py /workspace/nox/agent/nox_ops/svc_selfheal.py | cut -c1-200 | head
echo "## WAVE1A presence in distill_v2.py"; grep -nEi 'NO_GAIN|replay|rollback|auto.?revert|ready_bulk|0\.90|0\.85|regress|2 *п\.п|max_axis_drop' /workspace/nox/distill_v2/code/distill_v2.py | cut -c1-180 | head -30
echo "## speed.json"; cat /workspace/nox/state/speed.json 2>/dev/null | cut -c1-600
echo "## RITUAL :18215"; pid=$(ss -ltnpH "sport = :18215" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "pid=$pid"; tr '\0' ' ' </proc/$pid/cmdline | cut -c1-200; echo; readlink /proc/$pid/cwd
grep -rnE '08:30|21:00|22:30|08:00|ritual' $(readlink /proc/$pid/cwd) --include=*.py --include=*.json --include=*.sh 2>/dev/null | grep -v node_modules | cut -c1-200 | head -25
echo "## supervisor of :18215"; ps -o pid,ppid,args -p $(ps -o ppid= -p $pid | tr -d ' ') 2>/dev/null | cut -c1-200
echo "## DONE"
