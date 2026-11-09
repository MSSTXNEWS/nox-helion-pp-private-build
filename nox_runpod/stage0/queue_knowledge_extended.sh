#!/usr/bin/env bash
# NOX Stage 2: durable continuation after complete Stage1 full-model merge, no parallel training.
set -Eeuo pipefail
ROOT=/workspace/nox
LOG="$ROOT/logs"
TOOLS="$ROOT/tools"
FIRST="$ROOT/models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json"
SECOND="$ROOT/models/NOX_9B_KNOWLEDGE_UNIFIED/NOX_UNIFIED_RECEIPT.json"
mkdir -p "$LOG" "$TOOLS"
exec 8>"$LOG/nox_stage2_extended.lock"
flock -n 8 || { echo NOX_STAGE2_ALREADY_RUNNING;exit 0; }
echo "NOX_STAGE2_EXTENDED_QUEUE_RUNNING $(date -u +%FT%TZ)" >>"$LOG/nox_stage2_extended.status"
deadline=$(($(date +%s)+86400))
while [ ! -s "$FIRST" ]; do
 if [ "$(date +%s)" -gt "$deadline" ]; then
  echo "STAGE1_UNFINISHED_AFTER_DEADLINE - no false success" >>"$LOG/nox_stage2_extended.status"
  exit 42
 fi
 sleep 30
done
# Don't interfere with a still-running stage1 (write/merge process).
while fuser "$LOG/nox_9b_mega.lock" >/dev/null 2>&1; do sleep 15; done
PY="$ROOT/prime9b-venv/bin/python"
test -x "$PY" && test -s "$TOOLS/nox_prime_9b.py" && test -s "$TOOLS/nox_9b_merge.py" || { echo "STAGE1_TOOLS_MISSING";exit 43; }
RESEARCH='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/0044b76ac48859ba19feece39f9ac56908124055/nox_runpod/stage0/nox_history_research.py'
STAGE2='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/4b27983e669a1ae05ba2ec57a446fb055768011a/nox_runpod/stage0/knowledge_after_merge.py'
curl -fLsS --retry 3 "$RESEARCH" -o "$TOOLS/nox_history_research.py.new"
curl -fLsS --retry 3 "$STAGE2" -o "$TOOLS/nox_knowledge_extended.py.new"
"$PY" -m py_compile "$TOOLS/nox_history_research.py.new" "$TOOLS/nox_knowledge_extended.py.new"
mv -f "$TOOLS/nox_history_research.py.new" "$TOOLS/nox_history_research.py"
mv -f "$TOOLS/nox_knowledge_extended.py.new" "$TOOLS/nox_knowledge_extended.py"
"$PY" -u "$TOOLS/nox_history_research.py" || echo "NONFATAL_RESEARCH_ERROR"
echo "NOX_STAGE2_KNOWLEDGE_EXTENDED_BEGIN $(date -u +%FT%TZ)" | tee -a "$LOG/nox_stage2_extended.status"
export NOX_KNOWLEDGE_PASSES=8
export NOX_KNOWLEDGE_VARIANTS=24
rc=0
"$PY" -u "$TOOLS/nox_knowledge_extended.py" || rc=$?
if [ "$rc" -ne 0 ]; then
 echo "STAGE2_FAILED_$rc - preserving all artifacts; no fake success" | tee -a "$LOG/nox_stage2_extended.status"
 exit "$rc"
fi
test -s "$SECOND" || { echo "STAGE2_NO_UNIFIED_MODEL";exit 44; }
"$PY" -u "$TOOLS/nox_history_research.py" || echo "NONFATAL_FINAL_HISTORY_ERROR"
echo "NOX_STAGE2_EXTENDED_COMPLETE_FULL_9B_SAVED $(date -u +%FT%TZ)" | tee -a "$LOG/nox_stage2_extended.status"
sync
# Stop after full stage1+stage2, not at stage1 completion.
if command -v runpodctl >/dev/null 2>&1; then
 runpodctl pod stop erkgy956g04n6c >>"$LOG/nox_stage2_extended.status" 2>&1 || echo "AUTOSTOP_UNAVAILABLE" >>"$LOG/nox_stage2_extended.status"
fi
