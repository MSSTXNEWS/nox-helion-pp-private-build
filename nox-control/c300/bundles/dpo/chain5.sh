#!/bin/bash
# K1: окно тишины после r038: STOP -> ответы Mistral/gpt-oss -> удаление моделей (после проверки) -> 4-bit база -> проверки -> ворота -> STOP снят
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python; L=$D/run5.log
trap 'rm -f $N/STOP; echo "$(date -u +%T) chain5: STOP снят" >> $L' EXIT
touch $N/STOP
for i in $(seq 1500); do
  if ! pgrep -f 'venv/bin/python.* distill_v2.py (gen|judge|prep|train)' >/dev/null; then break; fi
  [ -e $N/agent/LIVE_TURN ] && sleep 5; sleep 10
done
echo "$(date -u +%T) chain5: окно. df: $(df -h /workspace | tail -1)" >> $L
dump(){ # dir name maxtok
  [ -d "$1" ] || return
  (cd $D && $PY -I teacher_dump.py $1 $2 $3 >> $L 2>&1); rc=$?; echo "$(date -u +%T) dump $2 rc=$rc" >> $L
  if [ $rc = 0 ] && [ -s $N/ops/teacher_answers/$2.jsonl ]; then
    if lsof +D "$1" >/dev/null 2>&1 || grep -q "$(basename $1)" $N/serve/llama-swap.yaml $N/state/orch_registry.json 2>/dev/null; then echo "SKIP удаления $1: используется" >> $L
    else s=$(du -sb $1 | cut -f1); rm -rf "$1" && echo "УДАЛЕНО $1 $s байт" >> $L; fi
  fi; }
dump $N/models/gpu/bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF mistral_small32 300
dump $N/models/gpu/unsloth/gpt-oss-20b-GGUF gpt_oss_20b 800
echo "$(date -u +%T) df: $(df -h /workspace | tail -1)" >> $L
FREE=$(df -BG --output=avail /workspace | tail -1 | tr -dc 0-9); [ "$FREE" -lt 24 ] && { echo "мало места для 4-bit ($FREE ГБ)" >> $L; exit 4; }
(cd $D && $PY -I quant4.py >> $L 2>&1); echo "$(date -u +%T) quant4 rc=$?" >> $L
if [ -s $N/models/student/Qwen3.6-35B-A3B-bnb4/bnb4_check.json ]; then
  B=$N/distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724
  (cd $D && NOX_MODEL=$N/models/student/Qwen3.6-35B-A3B-bnb4 $PY -I gates_only.py $B $B >> $L 2>&1); echo "$(date -u +%T) gates на bnb4 rc=$?" >> $L
fi
