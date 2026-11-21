#!/bin/bash
# c72: обучение не должно простаивать. Если DONE старше 6 ч и датасет не менялся -> новый цикл с лучшего адаптера, LR ниже. Защита качества и STOP-флаги сохраняются. Бэкап обёртки: .bak_c72
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-220; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag /root/nox/program/STOP /workspace/NOX_STOP; do [ -e $s ] && { echo "STOP $s -> hold"; exit 0; }; done
W=/root/nox/scripts/run_train_t131u.sh; [ -e $W.bak_c72 ] || cp $W $W.bak_c72
python3 - <<'PY'
p='/root/nox/scripts/run_train_t131u.sh'; s=open(p).read()
if 'RETRAIN_AFTER' not in s:
    old='  if [ "$cur" = "$last" ]; then echo'
    new='  age=$(( $(date +%s) - $(stat -c %Y $OUT/DONE) )); RETRAIN_AFTER=${RETRAIN_AFTER:-21600}\n  if [ "$cur" = "$last" ] && [ "$age" -ge "$RETRAIN_AFTER" ]; then echo "$(date -Is) DONE older than ${RETRAIN_AFTER}s: new cycle from best adapter, lower LR"; export LR=${LR:-2e-5}; last=force; fi\n  if [ "$cur" = "$last" ]; then echo'
    assert old in s; s=s.replace(old,new,1); open(p,'w').write(s)
PY
bash -n $W && echo wrapper ok
OUT=/root/nox/lora/qwen35_9b_t131u; ls -la --time-style=+%m-%d_%H:%M $OUT/DONE | awk '{print "DONE",$6,$7}'
supervisorctl start nox-train-qwen9b-t131u | a; sleep 100
tail -n 6 /root/nox/logs/train_qwen9b_t131u.log | a
supervisorctl status nox-train-qwen9b-t131u | awk '{print $1,$2}'; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo "== disk"; df -h / | tail -1 | awk '{print $4,$5}'
python3 -c "
import json,collections
s=json.load(open('/root/nox/state/dispatcher/state.json'))['tasks'];print(collections.Counter(t.get('status') for t in s.values()))"
