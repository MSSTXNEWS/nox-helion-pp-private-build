echo "K1: dpofix5"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo
echo "lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0)"
cd $D && setsid nohup bash $D/char_cycle.sh >> $N/agent/autotrain/char_cycle.log 2>&1 < /dev/null &
for i in 1 2 3 4 5 6 7 8; do sleep 40; echo "t=$((i*40)) procs: $(ps -eo stat,args | grep -E 'train_dpo|body_restart' | grep -v grep | awk '{print $1,$2,$3,$4}' | sed 's#/[^ ]*/##g' | tr '\n' ';') vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) 8104=$(curl -s -o /dev/null -m 3 -w %{http_code} http://127.0.0.1:8104/health)"; pgrep -f 'python -I train_dpo.py' >/dev/null && break; done
grep -h 'mix rows' $D/run7.log | tail -1
tail -4 $N/agent/autotrain/char_cycle.log | cut -c1-150
echo END
