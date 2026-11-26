#!/usr/bin/env bash
# NOX DPO окно: одной командой. bash /workspace/nox/ops/dpo/run_dpo.sh [dry]
# Условие: раунд autotrain завершён и новый не стартовал: touch /workspace/nox/STOP (после r033), дождаться busy()=false.
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python; L=$D/run.log
exec 8>$D/run.lock; flock -n 8 || { echo busy; exit 1; }
if pgrep -f 'distill_v2.py (gen|judge|prep|train)' >/dev/null; then echo "обучение идёт — не запускаю" | tee -a $L; exit 2; fi
FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "${FREE:-0}" -lt 20000 ] && { echo "мало VRAM ($FREE МиБ), нужна пауза" | tee -a $L; exit 3; }
df -BG --output=avail $N | tail -1 | tr -dc 0-9 | { read g; [ "$g" -lt 15 ] && { echo "диск <15 ГБ" | tee -a $L; exit 4; }; }
ARG=""; [ "$1" = dry ] && ARG="--dry"
echo "$(date -u +%T) build" >> $L; $PY -I $D/build_dpo.py --persona-gen ${PERSONA_GEN:-0} >> $L 2>&1
echo "$(date -u +%T) train $ARG" >> $L; (cd $D && $PY -I train_dpo.py $ARG >> $L 2>&1); echo "rc=$?" >> $L; tail -3 $L
# ворота на свежем кандидате (после полного прогона; для dry пропускаем)
if [ -z "$ARG" ]; then C=$(ls -td $N/distill_v2/ckpt_keep/cand_dpo_* 2>/dev/null | head -1); [ -n "$C" ] && { echo "$(date -u +%T) gates $C" >> $L; (cd $D && $PY -I gates_only.py $C >> $L 2>&1); tail -3 $L; }; fi
