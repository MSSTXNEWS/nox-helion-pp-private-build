#!/usr/bin/env bash
set -Eeuo pipefail
# NOX stage-0 CUDA smoke: genuine optimizer updates on two explicitly non-sensitive test examples.
# Never declare this distilled model or promote it to production.
ROOT=/workspace/nox
OUT="$ROOT/checkpoints/stage0_smoke"
MODEL="$ROOT/models/NOX_PRIME_9B_INHERITED"
VENV="$ROOT/train-venv"
mkdir -p "$ROOT"/{data,checkpoints,tools}
echo "NOX STAGE 0 GPU SMOKE: preflight"
test -f "$MODEL/config.json" || { echo "BLOCKED: source config missing"; exit 11; }
test "$(find "$MODEL" -maxdepth 1 -type f -name '*.safetensors' | wc -l)" -eq 4 || { echo "BLOCKED: need 4 verified weight shards"; exit 12; }
test "$(df -P /workspace | awk 'END{print $6}')" = "/workspace" || { echo "BLOCKED: no persistent /workspace"; exit 13; }
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
test -x "$VENV/bin/python" || { echo "BLOCKED: training venv missing; first install dependencies"; exit 14; }
"$VENV/bin/python" -m pip check || { echo "BLOCKED: pip dependency conflicts"; exit 15; }
"$VENV/bin/python" -c 'import transformers,peft,accelerate,bitsandbytes,datasets,torch; from transformers import Qwen3_5ForConditionalGeneration; assert torch.cuda.is_available(); print("LIBRARIES_AND_CUDA_PASS",transformers.__version__)'
# These two generic examples are ONLY an engineering test of the optimizer/checkpoint, NOT teacher-generated training data.
DATA="$ROOT/data/stage0_smoke_only.jsonl"
cat > "$DATA" <<'JSONL'
{"text":"Пользователь: Назови одно преимущество проверки checkpoint.\nАссистент: Проверка позволяет убедиться, что результат обучения сохранён и читается без повреждений."}
{"text":"Usuario: ¿Para qué sirve una copia de seguridad?\nAsistente: Permite recuperar los archivos después de una pérdida de datos."}
JSONL
TRAINER="$ROOT/tools/train_stage0.py"
curl -fLsS --retry 3 --connect-timeout 15 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-runpod-trainer-stage0/nox_runpod/stage0/train_stage0.py' -o "$TRAINER"
test -s "$TRAINER"
"$VENV/bin/python" -m py_compile "$TRAINER"
echo "Starting real 2-step GPU QLoRA optimizer smoke, NOT distillation"
set +e
timeout --signal=INT --kill-after=60s 1200s "$VENV/bin/python" -u "$TRAINER" --model "$MODEL" --data "$DATA" --out "$OUT" --max-steps 2 --save-steps 1 --seq-len 128 2>&1 | tee "$ROOT/checkpoints/stage0_smoke_output.log"
status=${PIPESTATUS[0]}
set -e
if [ "$status" -ne 0 ]; then
 echo "TRAINING_FAILED exit=$status. Do not use or promote output. Stop billing in RunPod."
 exit "$status"
fi
test -f "$OUT/result.json" || { echo "BLOCKED: no result.json"; exit 16; }
test -f "$OUT/adapter_unvalidated/adapter_config.json" || { echo "BLOCKED: adapter not persisted"; exit 17; }
echo "REAL_STEPS_FINISHED_NOT_VALIDATED. Download adapter and run quality tests. Stop the paid Pod."
