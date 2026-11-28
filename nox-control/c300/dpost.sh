echo "K1: dpost"; N=/workspace/nox; D=$N/ops/dpo
echo "procs: $(ps -eo pid,ppid,stat,etimes,args | grep -E 'char_cycle|train_dpo|rel_gates|body_restart' | grep -v grep | awk '{print $1,$2,$3,$4,$5,$6,$7}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
echo "lock holders: $(fuser $D/char_cycle.lock 2>&1 | tr '\n' ' ')"
echo "lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0)"
tail -8 $N/agent/autotrain/char_cycle.log | cut -c1-160
echo "run7 size $(stat -c %s $D/run7.log) tail:"; tail -5 $D/run7.log | cut -c1-160
echo "vram $(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits) pending=$([ -f $N/state/p3/dpo_pending ] && echo 1 || echo 0) chat_hold_age=$(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) ))"
echo END
