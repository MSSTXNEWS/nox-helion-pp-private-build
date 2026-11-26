#!/bin/bash
# K1: DPO раунд 2 (целевой) цепочкой: STOP -> ждать конца раунда -> пары (донор) -> DPO от cand_dpo_11260749 -> ворота -> ext-ворота (база/cand1/cand2) -> taef1+bench_sd -> снять STOP
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python; L=$D/run2.log
trap 'rm -f $N/STOP; echo "$(date -u +%T) chain4: STOP снят" >> $L' EXIT
touch $N/STOP
for i in $(seq 1500); do
  if ! pgrep -f 'distill_v2.py (gen|judge|prep|train)' >/dev/null && ! pgrep -f 'agent/ckpt_guard.py' >/dev/null; then break; fi
  sleep 15
done
echo "$(date -u +%T) chain4: окно, пары от донора" >> $L
(cd $D && $PY -I build_dpo2.py 80 600 >> $L 2>&1) ; echo "$(date -u +%T) build2 rc=$?" >> $L
[ -s $D/dpo2_train.jsonl ] || { echo "нет пар" >> $L; exit 1; }
FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "${FREE:-0}" -lt 20000 ] && { echo "мало VRAM $FREE" >> $L; exit 3; }
C1=$N/distill_v2/ckpt_keep/cand_dpo_11260749
(cd $D && $PY -I train_dpo.py --init-adapter $C1 --data $D/dpo2_train.jsonl --eval $D/dpo2_eval.jsonl --steps 44 >> $L 2>&1); echo "$(date -u +%T) train2 rc=$?" >> $L
C2=$(ls -td $N/distill_v2/ckpt_keep/cand_dpo_[0-9]* 2>/dev/null | grep -v trainer | head -1); echo "cand2=$C2" >> $L
cp $D/dpo_report.json $D/dpo_report_round2.json 2>/dev/null
[ "$C2" != "$C1" ] && { (cd $D && $PY -I gates_only.py $C2 >> $L 2>&1); echo "$(date -u +%T) gates2 rc=$?" >> $L
  B=$N/distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724
  (cd $D && $PY -I ext_eval.py $B $C1 $C2 >> $L 2>&1); echo "$(date -u +%T) ext rc=$?" >> $L; }
[ -s $N/models/flux/taef1.safetensors ] || curl -sL -m 120 -o $N/models/flux/taef1.safetensors https://huggingface.co/madebyollin/taef1/resolve/main/diffusion_pytorch_model.safetensors; ls -la $N/models/flux/taef1.safetensors >> $L 2>&1
bash $N/ops/draw/bench_sd.sh >> $L 2>&1; echo "$(date -u +%T) bench rc=$?" >> $L
