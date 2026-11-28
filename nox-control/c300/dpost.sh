echo "K1: dpost"; N=/workspace/nox; D=$N/ops/dpo
echo "procs: $(ps -eo pid,ppid,stat,etimes,args | grep -E 'char_cycle|train_dpo|rel_gates|body_restart|mix_data' | grep -v grep | awk '{print $1,$3,$4,$5,$6,$7}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
tail -10 $N/agent/autotrain/char_cycle.log | cut -c1-150
grep -h 'mix rows' $D/run7.log | tail -1; echo "run7 size $(stat -c %s $D/run7.log)"
tail -3 $D/run7.log | tr '\r' '\n' | tail -2 | cut -c1-150
echo "vram $(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits) body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' ' ' </proc/$P/cmdline | grep -o -- '--n-cpu-moe [0-9]*' | awk '{print $2}')"
echo "chat_hold_age=$(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold 2>/dev/null || echo 0) )) LIVE=$([ -e $N/agent/LIVE_TURN ] && echo 1 || echo 0)"
echo END
