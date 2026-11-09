#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/workspace/nox
TOOLS="$ROOT/tools"
LOG="$ROOT/logs"
STATE="$ROOT/checkpoints/nox_genesis_stage0"
mkdir -p "$TOOLS" "$LOG" "$STATE"
POD_ID=rsjmb616w0tqio
TEACHER_DATA="$ROOT/distillation/embryo_v1/9b_teacher_corpus.jsonl"
EMBRYO="$ROOT/embryo/NOX_EMBRYO_TRANSFER_STAGE"
MODEL="$ROOT/models/NOX_PRIME_9B_INHERITED"
TRAIN_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/b4e921dc969bdb82af6cab9fcf230d643309e0b6/nox_runpod/stage0/train_original_embryo.py"
status=1
stop_compute() {
  echo "NOX_STOP_REQUEST: training ended with status=$status, stopping GPU compute."
  sync
  if command -v runpodctl >/dev/null 2>&1; then
    runpodctl pod stop "$POD_ID" && return 0
  fi
  echo "RUNPOD_AUTOSTOP_FAILED: please stop pod manually. Output remains on /workspace."
}
trap 'status=$?; stop_compute' EXIT
trap 'echo "NOX_INTERRUPTED"; exit 130' INT TERM
test -f "$EMBRYO/embryo_manifest.json" || { echo "HOLD: original Embryo absent"; exit 11; }
test -f "$MODEL/transfer_manifest.json" || { echo "HOLD: original 9B manifest absent"; exit 12; }
test -s "$TEACHER_DATA" || { echo "HOLD: teacher corpus empty"; exit 13; }
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo "HOLD: /workspace not persistent mount"; exit 14; }
PYTHON="$ROOT/genesis-venv/bin/python"
test -x "$PYTHON" || { echo "HOLD: existing genesis Python environment missing"; exit 15; }
curl --fail --location --silent --show-error --retry 3 "$TRAIN_URL" -o "$TOOLS/train_original_embryo.py.new"
"$PYTHON" -m py_compile "$TOOLS/train_original_embryo.py.new"
mv "$TOOLS/train_original_embryo.py.new" "$TOOLS/train_original_embryo.py"
echo "NOX_EMBRYO_TRAINING_BEGIN: original model, Qwen3.5-9B teacher corpus, 120 optimizer steps"
# Hard time ceiling to avoid an endless bill if CUDA kernels hang. This is not an automatic retry.
timeout --signal=INT --kill-after=90s 14400s "$PYTHON" -u "$TOOLS/train_original_embryo.py" --steps 120 --context 128
status=$?
if [ "$status" -eq 0 ]; then
  test -s "$STATE/embryo_stage0_trained.safetensors" || { echo "FAILED: checkpoint absent"; exit 16; }
  test -s "$STATE/stage0_receipt.json" || { echo "FAILED: receipt absent"; exit 17; }
  echo "NOX_EMBRYO_WEIGHTS_UPDATED_UNVALIDATED"
else
  echo "NOX_EMBRYO_TRAIN_FAILED exit=$status"
fi
exit "$status"
