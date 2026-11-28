echo "K1: dpresume"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo; ST=$N/state/p3; A=$N/agent/autotrain
[ -f $ST/dpo_pending.hold_q27b ] && mv $ST/dpo_pending.hold_q27b $ST/dpo_pending; touch $ST/dpo_pending
echo "pending=$([ -f $ST/dpo_pending ] && echo 1 || echo 0) lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0) ttft_off=$([ -e $N/state/body_ttft_upgrade.off ] && echo 1 || echo 0)"
cd $D && setsid nohup bash $D/char_cycle.sh >> $A/char_cycle.log 2>&1 < /dev/null &
for i in 1 2 3 4 5 6; do sleep 30; pgrep -f 'python -I train_dpo.py' >/dev/null && break; done; sleep 60
grep -h 'mix rows' $D/run7.log | tail -1
UM=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits); echo "vram $UM pct=$(( ${UM%%,*}*100/${UM##*, } )) 8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) trainer=$(pgrep -fc 'python -I train_dpo.py')"
tail -4 $A/char_cycle.log | cut -c1-150; echo END
