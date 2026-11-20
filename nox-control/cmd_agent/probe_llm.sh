#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-400; }
echo "== llama-server cmd"; ps -eo args | grep "[l]lama-server -m /root/nox/models/deepseek" | a
echo "== cpu"; nproc; lscpu | grep -E "Model name|Thread|Socket|NUMA node\(s\)" | a
echo "== gpu"; nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader; nvidia-smi topo -m 2>/dev/null | head -4 | a
echo "== hugepages"; grep -E "HugePages_Total|Hugepagesize" /proc/meminfo; cat /sys/kernel/mm/transparent_hugepage/enabled
echo "== llama build"; /root/build/llama.cpp-sm70-build/bin/llama-server --version 2>&1 | head -2 | a
echo "== other llama procs"; ps -eo pid,rss,args | grep -E "[l]lama" | cut -c1-120
echo "== train procs"; supervisorctl status | grep -iE "train|distill|lora|forge|learn" | a
