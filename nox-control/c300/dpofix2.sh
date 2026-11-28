echo "K1: dpofix2"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo
for P in $(pgrep -f 'bash .*char_cycle.sh'); do kill -9 $P && echo "killed $P"; done; sleep 2
echo "lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0)"
cd $D && setsid nohup bash $D/char_cycle.sh >> $N/agent/autotrain/char_cycle.log 2>&1 < /dev/null &
sleep 90
echo "procs: $(ps -eo pid,ppid,stat,etimes,args | grep -E 'char_cycle|train_dpo|body_restart|mix_data' | grep -v grep | awk '{print $1,$3,$4,$5,$6,$7}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
tail -6 $N/agent/autotrain/char_cycle.log | cut -c1-140
grep -h 'mix rows' $D/run7.log | tail -1
echo "vram $(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)"; echo END
