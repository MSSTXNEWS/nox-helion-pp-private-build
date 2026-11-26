echo "C300: srv_k127"
N=/workspace/nox; D=$N/ops/dpo; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo
curl -sfL "$R/quant4.py?cb=$(date +%s)" -o $D/quant4.py && python3 -m py_compile $D/quant4.py && echo deployed
cat > $D/chain6.sh <<'SH'
#!/bin/bash
N=/workspace/nox; D=$N/ops/dpo; L=$D/run6.log
trap 'rm -f $N/STOP; echo "$(date -u +%T) chain6: STOP снят" >> $L' EXIT
touch $N/STOP; rm -rf $N/models/student/Qwen3.6-35B-A3B-bnb4
for i in $(seq 300); do pgrep -f 'venv/bin/python.* distill_v2.py (gen|judge|prep|train)' >/dev/null || break; sleep 10; done
echo "$(date -u +%T) chain6 старт; mem: $(free -g | sed -n 2p)" >> $L
( cd $D; $N/venv/bin/python -I quant4.py >> $L 2>&1; echo "$(date -u +%T) quant4 rc=$?" >> $L ) &
QP=$!; while kill -0 $QP 2>/dev/null; do echo "$(date -u +%T) rss: $(ps -o rss= -C python -C python3 --sort=-rss | head -1) KB; free: $(free -g | sed -n 2p | awk '{print $4}') GB; dst: $(du -sm $N/models/student/Qwen3.6-35B-A3B-bnb4 2>/dev/null | cut -f1) MB" >> $L; sleep 20; done
echo "$(date -u +%T) dmesg: $(dmesg 2>/dev/null | grep -i 'killed process\|out of memory' | tail -2)" >> $L
if [ -s $N/models/student/Qwen3.6-35B-A3B-bnb4/bnb4_check.json ]; then
  B=$N/distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724
  (cd $D && NOX_MODEL=$N/models/student/Qwen3.6-35B-A3B-bnb4 $N/venv/bin/python -I gates_only.py $B $B >> $L 2>&1); echo "$(date -u +%T) gates bnb4 rc=$?" >> $L
fi
SH
chmod +x $D/chain6.sh; nohup setsid $D/chain6.sh </dev/null >/dev/null 2>&1 &
sleep 30; tail -c 300 $D/run6.log
