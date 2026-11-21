#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-220; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && echo "STOP flag $s (hold)"; done
echo "== train"; supervisorctl status nox-train-qwen9b-t131u nox-train-keeper | awk '{print $1,$2}'
tail -n 5 /root/nox/logs/train_qwen9b_t131u.log | a; tail -n 2 /root/nox/logs/train_keeper.log | a
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo "== disk"; df -h / | tail -1 | awk '{print $4,$5}'
echo "== tasks"; python3 -c "
import json,collections
s=json.load(open('/root/nox/state/dispatcher/state.json'))['tasks'];print(collections.Counter(t.get('status') for t in s.values()))"
echo "== svc"; supervisorctl status | grep -vE "RUNNING" | awk '{print $1,$2}' | head -12
