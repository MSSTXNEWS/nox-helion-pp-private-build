#!/usr/bin/env bash
# NOX 9B autonomous three-pass genesis; RunPod Pod erkgy956g04n6c.
set -Eeuo pipefail
ROOT=/workspace/nox
POD=erkgy956g04n6c
TOOLS="$ROOT/tools"
LOG="$ROOT/logs"
mkdir -p "$TOOLS" "$LOG"
exec 9>"$LOG/nox_9b_mega.lock"
flock -n 9 || { echo "NOX_9B_ALREADY_RUNNING"; exit 0; }
# NO AUTO-STOP HERE. GPU must stay running for queued NOX knowledge learning.
# Stop is permitted only by an explicitly armed final supervisor after both stages.
on_exit(){
  local rc=$?
  trap - EXIT
  sync
  echo "NOX_STAGE1_EXIT code=$rc $(date -u +%FT%TZ); GPU_LEFT_RUNNING_FOR_STAGE2" >> "$LOG/nox_9b_stage1.log"
  exit "$rc"
}
trap on_exit EXIT
test -s "$ROOT/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json" || { echo "HOLD_NO_9B"; exit 31; }
test -s "$ROOT/embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json" || { echo "HOLD_NO_EMBRYO"; exit 32; }
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo "HOLD_VOLUME_NOT_MOUNTED"; exit 33; }
command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
PY="$ROOT/prime9b-venv/bin/python"
if [ ! -x "$PY" ]; then python3 -m venv --system-site-packages "$ROOT/prime9b-venv"; fi
"$PY" -m pip install --disable-pip-version-check -q 'transformers>=5.19,<6' 'accelerate>=1.10,<2' 'bitsandbytes>=0.48,<1' 'peft>=0.17,<1' 'safetensors>=0.4' 'sentencepiece>=0.2'
BASE_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/"
curl -fLsS --retry 3 "${BASE_URL}3d6a2f0f766f60bc9293e7ee02f3f5c5ca96c0d2/nox_runpod/stage0/prime_9b_genesis_full.py" -o "$TOOLS/nox_prime_9b.py.new"
curl -fLsS --retry 3 "${BASE_URL}31b101189bc6a7cd54814a4767a1d4262d7c68d2/nox_runpod/stage0/merge_nox_9b_full.py" -o "$TOOLS/nox_9b_merge.py.new"
"$PY" -m py_compile "$TOOLS/nox_prime_9b.py.new" "$TOOLS/nox_9b_merge.py.new"
mv "$TOOLS/nox_prime_9b.py.new" "$TOOLS/nox_prime_9b.py"
mv "$TOOLS/nox_9b_merge.py.new" "$TOOLS/nox_9b_merge.py"
echo "NOX_9B_TEACHER_TO_FOUNDATION_BEGIN $(date -u +%FT%TZ)"
attempt=1
while [ "$attempt" -le 3 ]; do
  echo "NOX_9B_TRAIN_ATTEMPT=$attempt"
  rc=0
  "$PY" -u "$TOOLS/nox_prime_9b.py" --teacher-exercises-per-topic 12 --passes 3 --context 512 --grad-accum 4 --lora-rank 32 || rc="$?"
  if [ "$rc" -eq 0 ]; then break; fi
  if [ "$attempt" -ge 3 ]; then exit "$rc"; fi
  if ! find "$ROOT/checkpoints/NOX_PRIME_9B_GENESIS" -name SUCCESS.json -print -quit 2>/dev/null | grep -q .; then
    echo "NO_CHECKPOINT_RETRY_NOT_SAFE";exit "$rc"
  fi
  attempt=$((attempt+1))
  sleep $((attempt*20))
done
echo "NOX_9B_FULL_WEIGHT_MERGE_BEGIN"
"$PY" -u "$TOOLS/nox_9b_merge.py"
test -s "$ROOT/models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json" || { echo "NOX_MERGE_RECEIPT_MISSING";exit 51; }
echo "NOX_9B_FULL_MODEL_SAVED; GPU_LEFT_RUNNING_FOR_STAGE2"
