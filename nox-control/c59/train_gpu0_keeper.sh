#!/bin/bash
# c59: тренер учится на GPU с наибольшей свободной памятью (GPU0 в приоритете), порог 12 ГБ; сторож обучения; поиск исполнителей.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-220; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && { echo "STOP flag $s -> exit"; exit 0; }; done
W=/root/nox/scripts/run_train_t131u.sh
[ -e $W.bak_c59 ] || cp $W $W.bak_c59
python3 - <<'PY'
p='/root/nox/scripts/run_train_t131u.sh'
s=open(p).read()
s=s.replace("export CUDA_VISIBLE_DEVICES=1 ","export ",1)
s=s.replace("MIN_FREE_MIB=${MIN_FREE_MIB:-22000}","MIN_FREE_MIB=${MIN_FREE_MIB:-12000}",1)
old=s[s.index("free=$(nvidia-smi"):s.index('echo "$cur" > $OUT/DATA_SHA\nexec')]
new='''f0=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0 | tr -d ' '); f1=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 1 | tr -d ' ')
if [ "${f0:-0}" -ge "${f1:-0}" ]; then GPU=0; free=$f0; else GPU=1; free=$f1; fi
if [ "${free:-0}" -lt "$MIN_FREE_MIB" ]; then echo "$(date -Is) best GPU$GPU free ${free}MiB < ${MIN_FREE_MIB} -> not starting"; exit 0; fi
export CUDA_VISIBLE_DEVICES=$GPU; echo "$(date -Is) training on GPU$GPU free ${free}MiB"
'''
s=s.replace(old,new,1)
open(p,'w').write(s)
PY
bash -n $W && echo "wrapper ok"; grep -n "CUDA_VISIBLE" /root/nox/scripts/train_qwen35_9b_t131u.py | head -3 | a
# keeper
cat > /root/nox/scripts/train_keeper.sh <<'K'
#!/bin/bash
# сторож обучения: каждые 10 минут, если тренер не работает и нет STOP — запускает; пишет причину в лог
L=/root/nox/logs/train_keeper.log
while true; do
  stop=""; for f in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag /root/nox/program/STOP; do [ -e $f ] && stop=$f; done
  st=$(supervisorctl status nox-train-qwen9b-t131u 2>/dev/null | awk '{print $2}')
  disk=$(df -BG / | tail -1 | awk '{gsub("G","",$4);print $4}')
  if [ -n "$stop" ]; then echo "$(date -Is) STOP $stop -> hold" >> $L
  elif [ "$st" = RUNNING ]; then echo "$(date -Is) running" >> $L
  elif [ "${disk:-0}" -lt 2 ]; then echo "$(date -Is) disk ${disk}G <2 -> hold" >> $L
  else echo "$(date -Is) trainer $st -> start" >> $L; supervisorctl start nox-train-qwen9b-t131u >> $L 2>&1; fi
  sleep 600
done
K
chmod +x /root/nox/scripts/train_keeper.sh
CD=$(dirname $(grep -rl "nox-train-qwen9b-t131u" /etc/supervisor 2>/dev/null | head -1)); echo "confdir $CD"
cat > $CD/nox-train-keeper.conf <<'C'
[program:nox-train-keeper]
command=/root/nox/scripts/train_keeper.sh
autostart=true
autorestart=true
stdout_logfile=/root/nox/logs/train_keeper.out
redirect_stderr=true
C
supervisorctl reread 2>&1 | tail -1; supervisorctl update 2>&1 | tail -2
echo "== train svc conf"; grep -h -A8 "program:nox-train-qwen9b" $CD/*.conf 2>/dev/null | grep -E "autorestart|startsecs|exitcodes|command" | a
ts=$(date +%s); OUT=/root/nox/lora/qwen35_9b_t131u
for m in $OUT/DONE $OUT/DATA_SHA; do [ -e $m ] && mv $m $m.bak_c59_$ts; done
supervisorctl start nox-train-qwen9b-t131u 2>&1 | tail -1 | a
sleep 90
echo "== log"; tail -n 8 /root/nox/logs/train_qwen9b_t131u.log 2>/dev/null | a
supervisorctl status | grep -E "train|keeper" | awk '{print $1,$2}'
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.free --format=csv,noheader
echo "== executors"; supervisorctl status | grep -iE "agent|exec|worker|sub" | awk '{print $1,$2}' | head -20
ls /root/nox/state 2>/dev/null | grep -iE "exec|queue|task|agent" | head -15
grep -rliE "executor|исполнител" /etc/supervisor 2>/dev/null | head -5
