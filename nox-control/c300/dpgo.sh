echo "K1: dpgo"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo; A=$N/agent/autotrain; ST=$N/state/p3
touch $ST/dpo_pending
echo "busy_match=$(pgrep -fc 'distill_v2.py (gen|judge|prep|train)|train_dpo.py|rel_gates.py|gates_only.py|ext_eval.py') lock2_free=$(flock -n $D/char_cycle2.lock true && echo 1 || echo 0)"
cd $D && setsid nohup bash $D/char_cycle.sh >> $A/char_cycle.log 2>&1 < /dev/null &
for i in $(seq 8); do sleep 30; pgrep -f 'python -I train_dpo.py' >/dev/null && break; done; sleep 110
UM=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits); echo "vram $UM pct=$(( ${UM%%,*}*100/${UM##*, } )) 8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) trainer=$(pgrep -fc 'python -I train_dpo.py') body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' ' ' </proc/$P/cmdline | grep -o -- '--n-cpu-moe [0-9]*' | awk '{print $2}')"
tail -5 $A/char_cycle.log | cut -c1-150; echo END
