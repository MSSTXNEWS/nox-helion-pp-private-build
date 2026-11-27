echo "K1: rs_fin"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; A=$N/agent/autotrain
cp -a $A/donor_hybrid.cmd $A/donor_hybrid.cmd.bak_rsfin_$(date +%s)
cp $A/donor_hybrid.t16.cmd $A/donor_hybrid.cmd
for k in 1 2 3 4 5 6 7 8; do bash $N/ops/body_restart.sh --force --cmd $A/donor_hybrid.cmd --reason "RESTART rs_fin: возврат -t 16 (8/10/12 не лучше в шуме)" 2>&1 | tail -1 | tee /tmp/rsf.o | cut -c1-120; grep -q "ИТОГ: ok" /tmp/rsf.o && break; sleep 30; done
echo "running: $(tr '\0' ' ' </proc/$(ss -ltnp | grep ':8104 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cmdline | grep -oE -- '-t [0-9]+')"
# обучение: nice 19 + ionice idle у DPO/ворот в char_cycle
C=$N/ops/dpo/char_cycle.sh; cp -a $C $C.bak_rs; sed -i 's/nice -n 5 \$PY/nice -n 19 ionice -c3 $PY/g' $C; bash -n $C && echo "char_cycle ok: $(grep -c 'nice -n 19 ionice -c3' $C)" || { cp -a $C.bak_rs $C; echo "char_cycle reverted"; }
for f in $N/ops/dpo/*.sh $N/agent/autotrain/autotrain.sh; do grep -l "nice -n [0-9]" $f 2>/dev/null; done | head
echo "owner_active: $(pgrep -f owner_active.py | wc -l) proc; $(tail -3 $N/state/orch/owner_active.log | cut -c1-120)"
echo "dpo_pending: $([ -f $N/state/p3/dpo_pending ] && echo yes || echo no); char_only: $([ -f $N/state/p3/char_only ] && echo yes || echo no); last_char_cycle: $(ls -t $N/logs/*char* $N/ops/dpo/run7.log 2>/dev/null | head -1)"
tail -4 $N/ops/dpo/run7.log 2>/dev/null | cut -c1-140
ps -eo ni,args | grep -E "train_dpo|rel_gates|distill_v2" | grep -v grep | cut -c1-100
