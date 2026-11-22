#!/bin/bash
ps -eo pid,ni,pcpu,nlwp,args --sort=-pcpu | head -8 | cut -c1-130
a=$(grep throttled_usec /sys/fs/cgroup/cpu.stat|cut -d' ' -f2); sleep 5; b=$(grep throttled_usec /sys/fs/cgroup/cpu.stat|cut -d' ' -f2); echo "throttled_us_in_5s=$((b-a))"
B=/root/nox/llama.cpp-f/build/bin/llama-server; $B --help 2>&1 | grep -E '^\s*(--spec|--n-cpu-moe|--cache-reuse|--slot-prompt|-kvu|--kv-unified)' | cut -c1-150 | head -24
$B --help 2>&1 | grep -iE 'mtp|draft-mtp|nextn' | cut -c1-160 | head -6
cd /root/nox/llama.cpp-f; grep -rln "nextn\|mtp" common tools/server src/llama-context.cpp 2>/dev/null | head -8
