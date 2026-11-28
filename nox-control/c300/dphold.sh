echo "K1: dphold"; N=/workspace/nox; D=$N/ops/dpo; ST=$N/state/p3
[ -f $ST/dpo_pending ] && mv $ST/dpo_pending $ST/dpo_pending.hold_q27b && echo "pending moved to hold"
for P in $(pgrep -f 'python -I train_dpo.py'); do kill -9 $P && echo "killed trainer $P"; done
for P in $(pgrep -f 'bash .*char_cycle.sh'); do kill -9 $P; done; sleep 3
echo "procs_left=$(pgrep -fc 'train_dpo|char_cycle.sh') lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0) hold=$([ -f $ST/dpo_pending.hold_q27b ] && echo 1 || echo 0)"
UM=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits); echo "vram $UM pct=$(( ${UM%%,*}*100/${UM##*, } )) 8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' ' ' </proc/$P/cmdline | grep -o -- '--n-cpu-moe [0-9]*' | awk '{print $2}')"
grep -h 'mix rows' $D/run7.log | tail -1; tail -3 $N/agent/autotrain/char_cycle.log | cut -c1-140
echo END
