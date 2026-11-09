#!/usr/bin/env bash
# One-shot NOX queue replacement. Does not touch Stage 1 or transfer.
set -Eeuo pipefail
ROOT=/workspace/nox
LOG="$ROOT/logs"
TOOLS="$ROOT/tools"
OLD_PID="$LOG/nox_9b_knowledge_queue.pid"
NEW_PID="$LOG/nox_stage2_extended.pid"
FIRST="$ROOT/models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json"
SECOND="$ROOT/models/NOX_9B_KNOWLEDGE_UNIFIED/NOX_UNIFIED_RECEIPT.json"
mkdir -p "$LOG" "$TOOLS"
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo "HOLD: /workspace not mounted"; exit 20; }
if [ -f "$NEW_PID" ] && kill -0 "$(cat "$NEW_PID")" 2>/dev/null; then
 echo "NOX_EXTENDED_QUEUE_ALREADY_RUNNING pid=$(cat "$NEW_PID")"
 exit 0
fi
# Running Stage2 cannot safely be patched at runtime; only replace if the FIRST
# model does not yet exist and old queue is therefore still waiting.
if [ -f "$OLD_PID" ] && kill -0 "$(cat "$OLD_PID")" 2>/dev/null; then
 old="$(cat "$OLD_PID")"
 args="$(ps -p "$old" -o args= || true)"
 case "$args" in
  *queue_knowledge_stage2.sh*)
    if [ -s "$FIRST" ]; then
      echo "HOLD: old stage2 may already be training. No replacement performed."
      exit 22
    fi
    echo "NOX_STOP_OLD_WAIT_ONLY pid=$old"
    kill -TERM "$old"
    for i in 1 2 3 4 5; do
      if ! kill -0 "$old" 2>/dev/null; then break; fi
      sleep 1
    done
    ;;
  *) echo "HOLD: unknown process in old queue PID file; no signal sent: $args";exit 23;;
 esac
fi
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/91b0c612d619f4ba2571b0cc98e0ae5104b544ec/nox_runpod/stage0/queue_knowledge_extended.sh'
curl -fLsS --retry 3 "$URL" -o "$TOOLS/queue_knowledge_extended.sh.new"
bash -n "$TOOLS/queue_knowledge_extended.sh.new"
mv -f "$TOOLS/queue_knowledge_extended.sh.new" "$TOOLS/queue_knowledge_extended.sh"
chmod 700 "$TOOLS/queue_knowledge_extended.sh"
nohup setsid bash "$TOOLS/queue_knowledge_extended.sh" </dev/null >> "$LOG/NOX_STAGE2_EXTENDED.log" 2>&1 &
pid=$!
echo "$pid" > "$NEW_PID"
sleep 2
if ! kill -0 "$pid" 2>/dev/null; then echo "QUEUE_FAILED";tail -n 20 "$LOG/NOX_STAGE2_EXTENDED.log"; exit 24; fi
echo "NOX_EXTENDED_QUEUE_DETACHED pid=$pid"
echo "NOX_STAGE1_UNTOUCHED; WINDOWS_MAY_DISCONNECT_AFTER_UPLOAD"
