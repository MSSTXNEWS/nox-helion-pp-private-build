echo "C300: srv_k56"
cat > /workspace/nox/ops/dpo/chain3.sh <<'C'
#!/bin/bash
# K1: после chain2 (DPO+ворота) — удержать STOP и прогнать bench_sd.sh в окне тишины, затем снять STOP
N=/workspace/nox; L=$N/ops/dpo/run.log
while pgrep -f chain2.sh >/dev/null; do sleep 3; done
touch $N/STOP; sleep 3
if pgrep -f 'distill_v2.py (gen|judge|prep|train)' >/dev/null; then echo "$(date -u +%T) chain3: SFT уже стартовал, bench пропущен" >> $L; exit 0; fi
echo "$(date -u +%T) chain3: bench_sd" >> $L
bash $N/ops/draw/bench_sd.sh >> $L 2>&1
echo "$(date -u +%T) chain3: bench rc=$?" >> $L
rm -f $N/STOP; echo "$(date -u +%T) chain3: STOP снят" >> $L
C
chmod +x /workspace/nox/ops/dpo/chain3.sh
nohup setsid /workspace/nox/ops/dpo/chain3.sh </dev/null >/dev/null 2>&1 &
sleep 2; pgrep -f chain3.sh | head -1
