#!/bin/bash
N=/workspace/nox
echo "== RssAnon/File/Shmem MB top"; for d in /proc/[0-9]*; do a=$(awk '/RssAnon/{print int($2/1024)}' $d/status 2>/dev/null); [ -n "$a" ] && [ "$a" -gt 700 ] && echo "$a $(awk '/RssFile/{print int($2/1024)}' $d/status) ${d#/proc/} $(tr '\0' ' ' <$d/cmdline | cut -c1-110)"; done | sort -rn | head -14 | sed 's/^/anon_file_pid: /'
echo "== meminfo"; grep -E "MemTotal|MemFree|MemAvailable|^Cached|AnonPages|Mapped|Shmem:|Active\(file\)|Inactive\(file\)" /proc/meminfo
echo "== donor hybrid cmd files"; cat $N/agent/autotrain/donor.env 2>/dev/null | sed -E 's/(KEY|TOKEN)=.*/\1=***/'; ls $N/agent/autotrain | grep -i -E "hybrid|cmd" ; for f in $N/agent/autotrain/donor_hybrid.cmd $N/agent/autotrain/donor.cmd; do [ -f $f ] && { echo "-- $f"; cut -c1-500 $f; }; done
echo "== autotrain hybrid handling"; grep -n -E "hybrid|donor_gpu|donor_h|nox.env|-t " $N/agent/autotrain/autotrain.sh | cut -c1-220 | head -25
echo "== nox.env"; cat $N/serve/nox.env $N/state/nox.env 2>/dev/null | head; grep -n "S=" $N/serve/serve_stack.sh | head -3
echo "== svc_selfheal: 8141/8106 entries"; grep -n -E "8141|8106|8142|8143" $N/agent/nox_ops/svc_selfheal.py | cut -c1-220 | head -20
echo "== nox_orch 8141 refs"; grep -n -E "8141|8142" $N/stewards/nox_orch.py $N/agent/nox_agents/mind/p0.py $N/agent/nox_agents/body_scan.py | cut -c1-200 | head
echo "== dual_judge.json"; cat $N/state/dual_judge.json | head -c 900
echo "== cpu_judges start.sh"; cut -c1-300 $N/ops/cpu_judges_20261125/start.sh | head -30
echo "== train_cpu_pause"; sed -n 1,30p $N/ops/train_cpu_pause.sh | cut -c1-200
echo "== who spawns 8106"; ps -o pid,ppid,etimes,args -p $(pgrep -f 'port 8106'|head -1) | cut -c1-200; pp=$(ps -o ppid= -p $(pgrep -f 'port 8106'|head -1)); ps -o pid,args -p $pp | cut -c1-200
echo "== 8106 users (scripts)"; grep -n "8106" $N/ops/liska_skill_teacher.py | head -3 | cut -c1-200
