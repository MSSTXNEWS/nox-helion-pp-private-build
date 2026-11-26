echo "C300: tr_watch1"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
cat > $D/watch1.sh <<'EOW'
#!/bin/bash
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python; L=$D/watch1.log
echo "$(date -u +%T) watch1 старт" >> $L
# 1) дождаться rel_gates -> принять через guard, если прошёл
while pgrep -f "rel_gates.py" >/dev/null; do sleep 30; done
SHA=ebf02c04001131ac
echo "$(date -u +%T) rel_gates закончил: $(python3 -c "import json;d=json.load(open('$N/distill_v2/gates/decision_$SHA.json'));print(d['pass'],d['reasons'][:3],d['rel']['ab'])" 2>&1 | cut -c1-500)" >> $L
$PY -I $D/accept_cand.py $SHA >> $L 2>&1; echo "$(date -u +%T) accept rc=$?" >> $L
# 2) пары DPO: повторять сбор, пока донор отвечает и пар < 800
for t in $(seq 12); do
  [ -f $N/state/p3/dpo_pending ] && break
  if curl -s -m5 localhost:8104/health | grep -q ok; then (cd $D && nice -n 8 $PY -I build_dpo3.py 110 >> $D/build3.log 2>&1); fi
  sleep 300
done
echo "$(date -u +%T) watch1 конец; pending=$([ -f $N/state/p3/dpo_pending ] && echo да || echo нет)" >> $L
EOW
chmod +x $D/watch1.sh
pgrep -f watch1.sh >/dev/null && echo "уже идёт" || { setsid -f nohup bash $D/watch1.sh >/dev/null 2>&1 < /dev/null; sleep 2; echo "watch1 pid $(pgrep -f watch1.sh | head -1)"; }
echo END
