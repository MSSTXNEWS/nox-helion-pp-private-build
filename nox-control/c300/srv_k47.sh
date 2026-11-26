echo "C300: srv_k47"
cat > /workspace/nox/ops/dpo/chain_full.sh <<'C'
#!/bin/bash
# SRV K1: ждёт конца раунда (STOP стоит) -> dry -> полный DPO -> ворота -> снимает STOP при любом исходе
N=/workspace/nox; D=$N/ops/dpo; L=$D/run.log
trap 'rm -f $N/STOP; echo "$(date -u +%T) chain: STOP снят" >> $L' EXIT
touch $N/STOP
for i in $(seq 1500); do
  if ! pgrep -f 'distill_v2.py (gen|judge|prep|train)' >/dev/null && ! pgrep -f 'agent/ckpt_guard.py' >/dev/null; then break; fi
  sleep 15
done
echo "$(date -u +%T) chain: GPU свободен, dry" >> $L
bash $D/run_dpo.sh dry >> $L 2>&1
if tail -n 5 $L | grep -q "^rc=0"; then
  echo "$(date -u +%T) chain: dry OK, полный прогон" >> $L
  bash $D/run_dpo.sh >> $L 2>&1
else echo "$(date -u +%T) chain: dry упал, стоп цепочки" >> $L; fi
C
chmod +x /workspace/nox/ops/dpo/chain_full.sh
nohup setsid /workspace/nox/ops/dpo/chain_full.sh </dev/null >/dev/null 2>&1 &
sleep 2; pgrep -f chain_full | head -1
