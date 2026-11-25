#!/bin/bash
echo "load $(cut -d' ' -f1-3 /proc/loadavg)"; free -m|sed -n 2p
echo "== guard alive"; cat /workspace/nox/state/p3/guard.pid; pgrep -fc p3_cpuset_guard
echo "== clients of 8104 (by local src port owner)"
for sp in $(ss -Htn state established '( dport = :8104 )' | awk '{print $4}' | sed 's/.*://'); do ss -Htnp state established "( sport = :$sp )" | grep -o 'users:.*' | head -1; done | sed 's/,fd=.*//' | sort | uniq -c
for pid in $(ss -Htnp state established '( dport = :8104 )' | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do echo "client pid $pid: $(tr '\0' ' ' </proc/$pid/cmdline | cut -c1-150)"; done
echo "== RSS top 20 (MB)"; ps -eo rss,pid,ni,etimes,args --sort=-rss | head -21 | awk '{r=int($1/1024); $1=""; print r" MB"$0}' | sed -E 's/(--api-key|--master-key|--key)[ =][^ ]+/\1 ***/g' | cut -c1-200
echo "== conns to other llama ports"; for p in 8106 8141 8142 8143 8151 8152 8811 8812 8300 8082; do echo "$p est=$(ss -Htn state established "( dport = :$p )" | wc -l)"; done
echo "== 8104 log tail"; ls -t /workspace/nox/agent/out/*8104* /tmp/*8104* /workspace/nox/state/*8104* 2>/dev/null | head -3; 
echo "== 8104 launcher"; grep -rl -- "--port 8104" /workspace/nox/ops /workspace/nox/serve /workspace/nox/agent 2>/dev/null | head -5
echo "== numastat/hugepages/thp"; cat /sys/kernel/mm/transparent_hugepage/enabled /proc/sys/vm/swappiness; ulimit -l; grep -E "HugePages_Total|MemAvailable|Cached|Mlocked" /proc/meminfo
