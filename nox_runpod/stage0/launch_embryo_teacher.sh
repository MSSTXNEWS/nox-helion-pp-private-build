#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/workspace/nox
URL=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-runpod-trainer-stage0/nox_runpod/stage0/embryo_from_9b_teacher.py
mkdir -p "$ROOT"/{tools,logs,distillation}
test -f "$ROOT/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json" || { echo "HOLD: model transfer manifest missing."; exit 21; }
test -f "$ROOT/embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json" || { echo "HOLD: original Embryo checkpoint missing."; exit 22; }
test "$(df -P /workspace | tail -n 1 | awk '{print $6}')" = /workspace || { echo "HOLD: /workspace not mounted"; exit 23; }
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
if [ ! -x "$ROOT/genesis-venv/bin/python" ]; then
  python -m venv --system-site-packages "$ROOT/genesis-venv"
fi
"$ROOT/genesis-venv/bin/python" -m pip install --disable-pip-version-check 'transformers>=5.19,<6' 'accelerate>=1.10,<2' 'bitsandbytes>=0.48,<1' 'huggingface-hub>=0.35,<2' 'sentencepiece>=0.2'
curl -fsSL --retry 2 --connect-timeout 15 "$URL" -o "$ROOT/tools/embryo_from_9b_teacher.py"
test -s "$ROOT/tools/embryo_from_9b_teacher.py"
"$ROOT/genesis-venv/bin/python" -m py_compile "$ROOT/tools/embryo_from_9b_teacher.py"
echo 'NOX_GENESIS: starting Qwen3.5-9B teacher generation for EXISTING Embryo V1'
set +e
"$ROOT/genesis-venv/bin/python" -u "$ROOT/tools/embryo_from_9b_teacher.py" 2>&1 | tee -a "$ROOT/logs/embryo_9b_genesis.log"
rc=${PIPESTATUS[0]}
set -e
if [ "$rc" -ne 0 ]; then echo "GENESIS_TEACHER_FAILED:$rc; no Embryo weight update claimed"; exit "$rc"; fi
echo 'GENESIS_TEACHER_READY - teacher corpus stored, student weights NOT yet updated.'
