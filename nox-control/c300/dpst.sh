echo "K1: dpst"; N=/workspace/nox; D=$N/ops/dpo; ST=$N/state/p3; A=$N/agent/autotrain
echo "procs: $(ps -eo pid,stat,etimes,args | grep -E 'char_cycle|train_dpo|rel_gates|body_restart' | grep -v grep | awk '{print $1,$2,$3,$4,$5}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
UM=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits); echo "vram $UM pct=$(( ${UM%%,*}*100/${UM##*, } )) 8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' ' ' </proc/$P/cmdline | grep -o -- '--n-cpu-moe [0-9]*' | awk '{print $2}')"
echo "pending=$([ -f $ST/dpo_pending ] && echo 1 || echo 0) hold=$([ -f $ST/dpo_pending.hold_q27b ] && echo 1 || echo 0) vram_abort=$([ -e $ST/dpo_vram_abort ] && echo 1 || echo 0) lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0) disk_G=$(df --output=avail -BG $N | tail -1 | tr -dc 0-9)"
tail -8 $A/char_cycle.log | cut -c1-150
grep -h 'mix rows' $D/run7.log | tail -1
tail -c 600 $D/run7.log | tr '\r' '\n' | tail -2 | cut -c1-140
ls -t $N/distill_v2/gates/decision_*.json | head -1 | sed 's#.*/##'
echo END
