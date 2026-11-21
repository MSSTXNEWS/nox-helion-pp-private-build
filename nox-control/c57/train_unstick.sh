#!/bin/bash
# c57: обучение адаптера Qwen9B стояло в idle из-за DONE-маркера + DATA_SHA, записанного c52 до запуска. Маркер переименовывается (не удаляется), обучение стартует через supervisor.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-200; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && { echo "STOP flag $s -> exit"; exit 0; }; done
S=/root/nox/scripts/train_qwen35_9b_t131u.py; OUT=/root/nox/lora/qwen35_9b_t131u
echo "== marker logic"; grep -nE "DONE|DATA_SHA|idle|unchanged" $S | head -14 | a
echo "== out dir"; ls -la --time-style=+%F_%T $OUT | awk '{print $5,$6,$7}' | tail -12
echo "== supervisor conf"; grep -rhE "^\[program:nox-train-qwen9b|^command|^environment" $(grep -rl "nox-train-qwen9b-t131u" /etc/supervisor 2>/dev/null | head -1) 2>/dev/null | a | head -5
ts=$(date +%s)
for m in $OUT/DONE $OUT/DONE.json $OUT/DONE.marker $OUT/DATA_SHA; do [ -e $m ] && { mv $m $m.bak_c57_$ts && echo "moved $m"; }; done
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0 | tr -d ' '); echo "GPU0 free ${free}MiB; disk: $(df -h / | tail -1 | awk '{print $4}') free"
supervisorctl start nox-train-qwen9b-t131u 2>&1 | tail -1 | a
sleep 120
echo "== log tail"; tail -n 8 /root/nox/logs/train_qwen9b_t131u.log 2>/dev/null | a
supervisorctl status nox-train-qwen9b-t131u | awk '{print $1,$2,$3,$4}'; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
