#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-230; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && { echo "STOP $s -> exit"; exit 0; }; done
W=/root/nox/scripts/run_train_t131u.sh
grep -q MICRO_BATCH $W || sed -i 's#^unset BNB_CUDA_VERSION#unset BNB_CUDA_VERSION\nexport MICRO_BATCH=${MICRO_BATCH:-1} EFF_BATCH=${EFF_BATCH:-8} GPU_FRACTION=${GPU_FRACTION:-0.93} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True#' $W
bash -n $W && echo wrapper ok; grep -n MICRO_BATCH $W | a
supervisorctl stop nox-train-qwen9b-t131u >/dev/null 2>&1; supervisorctl start nox-train-qwen9b-t131u | a
sleep 150
tail -n 5 /root/nox/logs/train_qwen9b_t131u.log | a
supervisorctl status nox-train-qwen9b-t131u | awk '{print $1,$2}'; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo "== blocked tasks"; python3 - <<'PY'
import json,collections
s=json.load(open('/root/nox/state/dispatcher/state.json'))['tasks']
b=[t for t in s.values() if t.get('status')in('blocked','failed')]
print(collections.Counter(str(t.get('blocked_reason') or t.get('error') or t.get('reason'))[:70] for t in b).most_common(6))
PY
