echo "K1: dpofix8"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo; A=$N/agent/autotrain; ST=$N/state/p3
awk 'p{print "36"; p=0; next} {print} $0=="--n-cpu-moe"{p=1}' $A/donor_hybrid.cmd.liska_ncmoe22 > $A/donor_hybrid.cmd.dpo_ncmoe36
echo "diff_lines=$(diff $A/donor_hybrid.cmd.liska_ncmoe22 $A/donor_hybrid.cmd.dpo_ncmoe36 | grep -c '^[<>]') lines=$(wc -l < $A/donor_hybrid.cmd.dpo_ncmoe36) has36=$(grep -cx 36 $A/donor_hybrid.cmd.dpo_ncmoe36)"
echo "pending=$([ -f $ST/dpo_pending ] && echo 1 || echo 0) abort=$([ -e $ST/dpo_vram_abort ] && echo 1 || echo 0) lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0) HYB_in_script=$(grep -c dpo_ncmoe36 $D/char_cycle.sh)"
cd $D && setsid nohup bash $D/char_cycle.sh >> $A/char_cycle.log 2>&1 < /dev/null &
for i in $(seq 8); do sleep 30; pgrep -f 'python -I train_dpo.py' >/dev/null && break; done; sleep 100
UM=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits); echo "vram $UM pct=$(( ${UM%%,*}*100/${UM##*, } )) 8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) trainer=$(pgrep -fc 'python -I train_dpo.py') body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' '\n' </proc/$P/cmdline | grep -x -A1 -- '--n-cpu-moe' | tail -1)"
tail -5 $A/char_cycle.log | cut -c1-150; echo END
