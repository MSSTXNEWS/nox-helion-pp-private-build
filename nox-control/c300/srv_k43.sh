echo "C300: srv_k43"
cat > /workspace/nox/ops/dpo/chain_dry.sh <<'C'
#!/bin/bash
N=/workspace/nox; L=$N/ops/dpo/run.log
for i in $(seq 240); do
  if ! pgrep -f 'distill_v2.py (gen|judge|prep|train)' >/dev/null && ! pgrep -f 'agent/ckpt_guard.py' >/dev/null; then break; fi
  sleep 15
done
echo "$(date -u +%T) chain: GPU свободен, dry" >> $L
bash $N/ops/dpo/run_dpo.sh dry >> $L 2>&1
echo "$(date -u +%T) chain: dry rc=$?" >> $L
C
chmod +x /workspace/nox/ops/dpo/chain_dry.sh; : > /workspace/nox/ops/dpo/run.log
setsid -f bash /workspace/nox/ops/dpo/chain_dry.sh </dev/null >/dev/null 2>&1
sleep 2; pgrep -f chain_dry | head -1
