#!/usr/bin/env bash
# NOX STAGE 2: separate detached queue, waits for unified full-size 9B Stage 1 model.
set -Eeuo pipefail
ROOT=/workspace/nox
LOG="$ROOT/logs"
TOOLS="$ROOT/tools"
FIRST="$ROOT/models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json"
SECOND="$ROOT/models/NOX_9B_KNOWLEDGE_UNIFIED/NOX_UNIFIED_RECEIPT.json"
LOCK="$LOG/nox_9b_knowledge_queue.lock"
POD=erkgy956g04n6c
mkdir -p "$LOG" "$TOOLS"
exec 8>"$LOCK"
flock -n 8 || { echo "NOX_STAGE2_QUEUE_ALREADY_RUNNING"; exit 0; }
finalize(){
 local code="$?"
 trap - EXIT
 echo "NOX_STAGE2_EXIT=$code $(date -u +%FT%TZ)" | tee -a "$LOG/nox_9b_knowledge.status"
 sync
 if [ "$code" -eq 0 ] && [ -s "$SECOND" ]; then
   echo "NOX_STAGE1_AND_STAGE2_COMPLETED: stop GPU after all stages" | tee -a "$LOG/nox_9b_knowledge.status"
   if command -v runpodctl >/dev/null 2>&1; then
      runpodctl pod stop "$POD" >>"$LOG/nox_9b_knowledge.status" 2>&1 || echo "AUTOSTOP_FAILED: RunPod may still bill" >>"$LOG/nox_9b_knowledge.status"
   else
      echo "AUTOSTOP_UNAVAILABLE: RunPod may still bill" >>"$LOG/nox_9b_knowledge.status"
   fi
 else
   echo "NOX_STAGE2_INCOMPLETE: GPU not automatically stopped by this queue; budget protection required" | tee -a "$LOG/nox_9b_knowledge.status"
 fi
 exit "$code"
}
trap finalize EXIT
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo "HOLD: /workspace not mounted"; exit 31; }
echo "NOX_STAGE2_QUEUED $(date -u +%FT%TZ)" | tee -a "$LOG/nox_9b_knowledge.status"
# Do not start stage2 until the FINAL verified full-size checkpoint appears.
# Bound queue wait to 12 h to avoid permanent unattended billing; do not fake stage 1 success.
deadline=$(( $(date +%s) + 43200 ))
while [ ! -s "$FIRST" ]; do
 if [ "$(date +%s)" -ge "$deadline" ]; then echo "NOX_STAGE1_NOT_READY_BEFORE_DEADLINE";exit 42; fi
 sleep 30
done
# Stage 1 may have moved files while merging. Read receipt from Python Stage 2.
echo "NOX_STAGE2_READY_AFTER_STAGE1 $(date -u +%FT%TZ)" | tee -a "$LOG/nox_9b_knowledge.status"
PY="$ROOT/prime9b-venv/bin/python"
test -x "$PY" || { echo "HOLD: stage1 python environment missing";exit 43; }
test -s "$TOOLS/nox_prime_9b.py" || { echo "HOLD: stage1 NOX trainer missing";exit 44; }
test -s "$TOOLS/nox_9b_merge.py" || { echo "HOLD: stage1 merger missing";exit 45; }
url="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/1dacd09280daa4bdccabf044059c09b2f95917b4/nox_runpod/stage0/knowledge_after_merge.py"
curl -fLsS --retry 4 --connect-timeout 15 "$url" -o "$TOOLS/nox_9b_knowledge_stage2.py.new"
"$PY" -m py_compile "$TOOLS/nox_9b_knowledge_stage2.py.new"
mv -f "$TOOLS/nox_9b_knowledge_stage2.py.new" "$TOOLS/nox_9b_knowledge_stage2.py"
attempt=1
while [ "$attempt" -le 3 ]; do
 echo "NOX_STAGE2_TRAIN_ATTEMPT=$attempt" | tee -a "$LOG/nox_9b_knowledge.status"
 rc=0
 "$PY" -u "$TOOLS/nox_9b_knowledge_stage2.py" || rc="$?"
 if [ "$rc" -eq 0 ] && [ -s "$SECOND" ]; then
   echo "NOX_STAGE2_FULL_9B_KNOWLEDGE_CHECKPOINT_SAVED" | tee -a "$LOG/nox_9b_knowledge.status"
   exit 0
 fi
 if [ "$attempt" -ge 3 ]; then
   echo "NOX_STAGE2_FAILED code=$rc";exit 46
 fi
 # Retry only if stage2 saved a durable training pass; architecture failures are not retryable.
 if ! find "$ROOT/checkpoints/NOX_9B_KNOWLEDGE" -name SUCCESS.json -print -quit 2>/dev/null | grep -q .; then
   echo "NOX_STAGE2_FAIL_CLOSED_WITHOUT_CHECKPOINT";exit 47
 fi
 attempt=$((attempt+1))
 sleep $((20*attempt))
done
