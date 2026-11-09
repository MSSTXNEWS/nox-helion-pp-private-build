#!/usr/bin/env bash
# NOX stage 2 queue installer. Run in a SECOND PowerShell; Windows may disconnect after ACK.
set -Eeuo pipefail
ROOT=/workspace/nox
TOOLS="$ROOT/tools"
LOG="$ROOT/logs"
QUEUE="$TOOLS/queue_knowledge_stage2.sh"
PID="$LOG/nox_9b_knowledge_queue.pid"
mkdir -p "$TOOLS" "$LOG"
if [ "$(df -P /workspace | tail -1 | awk '{print $6}')" != "/workspace" ]; then
 echo "HOLD: persistent network /workspace not mounted";exit 51
fi
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
 echo "NOX_STAGE2_QUEUE_ALREADY_RUNNING pid=$(cat "$PID")"
 exit 0
fi
# If a queue already owns the lock, leave it; no second process.
if command -v fuser >/dev/null 2>&1 && fuser "$LOG/nox_9b_knowledge_queue.lock" >/dev/null 2>&1; then
 echo "NOX_STAGE2_QUEUE_LOCKED";exit 0
fi
curl -fLsS --retry 4 --connect-timeout 15 \
 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/e70b7ef9deb90e9dc0c0b4d110bcc33493eba771/nox_runpod/stage0/queue_knowledge_stage2.sh' \
 -o "$QUEUE.new"
bash -n "$QUEUE.new"
mv -f "$QUEUE.new" "$QUEUE"
chmod 700 "$QUEUE"
nohup setsid bash "$QUEUE" </dev/null >>"$LOG/NOX_9B_KNOWLEDGE_QUEUE.log" 2>&1 &
qpid=$!
echo "$qpid" >"$PID"
sleep 2
if ! kill -0 "$qpid" 2>/dev/null; then
 echo "NOX_STAGE2_QUEUE_START_FAILED"
 tail -n 20 "$LOG/NOX_9B_KNOWLEDGE_QUEUE.log" || true
 exit 52
fi
echo "NOX_STAGE2_QUEUE_PERSISTENT_STARTED pid=$qpid"
echo "STAGE2_WILL_WAIT_FOR=/workspace/nox/models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json"
echo "WINDOWS_CAN_DISCONNECT; VERIFY TRAINING IN /workspace/nox/logs/NOX_9B_KNOWLEDGE_QUEUE.log"
