#!/usr/bin/env bash
# NOX A40 one-pass recovery from real backward CUDA OOM; NO-LOSS checkpoint policy.
set -Eeuo pipefail
R=/workspace/nox
B=$R/dispatcher/nox_v3/bin
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110
mkdir -p "$B" "$R/logs"
exec 8>/opt/nox_a40_megaforge.lock
flock -n 8 || { echo HOLD_RECOVERY_ALREADY_ACTIVE;exit 2; }
echo === DISABLE_KNOWN_LEGACY_GPU_WORKER ===
curl -fsSL --retry 3 "$BASE/nox_runpod/v3/nox_emergency_takeover.py" -o /tmp/nox_a40_handoff.py
python3 -m py_compile /tmp/nox_a40_handoff.py
python3 /tmp/nox_a40_handoff.py --node A40 || echo HOLD_HANDOFF_CHECK_STATUS
echo === UPDATE_BACKWARD_OOM_FIX ===
curl -fsSL --retry 3 "$BASE/nox_runpod/stage0/a40_full_parameter_distill_cycle.py" -o /tmp/nox_a40_trainer.py
python3 -m py_compile /tmp/nox_a40_trainer.py
install -m 644 /tmp/nox_a40_trainer.py "$B/a40_full_parameter_distill_cycle.py"
curl -fsSL --retry 3 "$BASE/nox_runpod/v3/nox_a40_direct_recovery.py" -o /tmp/nox_a40_direct_recovery.py
python3 -m py_compile /tmp/nox_a40_direct_recovery.py
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
echo === GPU_OWNERS_AFTER_HANDOFF ===
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader || true
echo === RUN_REAL_ALL_PARAMETER_STUDENT ===
python3 /tmp/nox_a40_direct_recovery.py || echo HOLD_LAUNCH_REQUIRE_LOG_REVIEW
echo === NEW_TRAINING_RECEIPT ===
cat "$R/dispatcher/a40_full_parameter/progress.json" 2>/dev/null || true
echo === GPU ===
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.free --format=csv,noheader || true
echo === LATEST_LOG ===
tail -n 14 "$R/logs/NOX_DIRECT_FULL_PARAMETER_A40.log" 2>/dev/null || true
