#!/usr/bin/env bash
# NOX Embryo V1 supervised training; does not modify original weights.
set -Eeuo pipefail
ROOT=/workspace/nox
RUN="$ROOT/tools/run_embryo_training_autostop.sh"
LOG="$ROOT/logs"
STATE="$ROOT/checkpoints/nox_genesis_stage0"
mkdir -p "$LOG" "$STATE"
POD=rsjmb616w0tqio
LOCK="$LOG/nox_embryo_supervisor.lock"
STATUS="$LOG/nox_embryo_supervisor.status"
attempt=1
max_attempts=3
start=$(date +%s)
max_seconds=14400
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "NOX_SUPERVISOR_LOCKED - avoiding duplicate train"
  exit 51
fi
cleanup(){ rmdir "$LOCK" 2>/dev/null || true; }
trap cleanup EXIT
stop_gpu(){
  sync
  if command -v runpodctl >/dev/null 2>&1; then
    runpodctl pod stop "$POD" >>"$LOG/nox_embryo_autostop.log" 2>&1 && return 0
  fi
  echo "NOX_STOP_FAILED: RunPod CLI not authorized, external safety stop scheduled" | tee -a "$LOG/nox_embryo_autostop.log"
  return 1
}
echo "RUNNING" > "$STATUS"
while [ "$attempt" -le "$max_attempts" ]; do
  elapsed=$(( $(date +%s)-start ))
  if [ "$elapsed" -gt "$max_seconds" ]; then echo "TIME_BUDGET_EXCEEDED"; break; fi
  echo "NOX_SUPERVISOR_ATTEMPT $attempt $(date -u +%FT%TZ)"
  rc=0
  bash "$RUN" || rc=$?
  if [ "$rc" -eq 0 ]; then
    if [ -s "$STATE/three_pass_result.json" ]; then
      echo "THREE_PASS_RESULT_SAVED" | tee "$STATUS"
    else
      echo "NOX_CYCLE_RETURNED_WITHOUT_THREE_PASS_RECEIPT" | tee "$STATUS"
    fi
    stop_gpu || true
    exit 0
  fi
  echo "NOX_ATTEMPT_FAILED code=$rc" | tee -a "$LOG/nox_embryo_errors.log"
  # Retry only failures where a saved GPU optimizer checkpoint can be resumed.
  resumable=0
  for p in pass1 pass2 pass3; do
    if [ -s "$STATE/$p/in_progress.pt" ] && [ -s "$STATE/$p/in_progress.safetensors" ]; then
       resumable=1
       break
    fi
  done
  if [ "$resumable" -ne 1 ]; then
    echo "NOX_UNRECOVERABLE_NO_VALID_CHECKPOINT" | tee "$STATUS"
    break
  fi
  attempt=$((attempt+1))
  [ "$attempt" -le "$max_attempts" ] || break
  sleep $((attempt*15))
done
echo "FAILED_STOPPING_GPU" | tee "$STATUS"
stop_gpu || true
exit 1
