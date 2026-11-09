#!/usr/bin/env bash
# NOX 9B first-stage detached launch; never re-transfer any weights.
set -Eeuo pipefail
R=/workspace/nox
LOG="$R/logs"
TOOLS="$R/tools"
mkdir -p "$LOG" "$TOOLS"
MODEL="$R/models/NOX_PRIME_9B_INHERITED"
EMBRYO="$R/embryo/NOX_EMBRYO_TRANSFER_STAGE"
test -s "$MODEL/transfer_manifest.json" || { echo 'HOLD: 9B transfer not completed'; exit 11; }
test -s "$EMBRYO/embryo_manifest.json" || { echo 'HOLD: Embryo transfer not completed'; exit 12; }
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo 'HOLD: persistent /workspace not mounted'; exit 13; }
# Do not launch twice even if old pidfile is stale.
LOCK="$LOG/nox_9b_mega.lock"
if command -v fuser >/dev/null 2>&1 && fuser "$LOCK" >/dev/null 2>&1; then
 echo "NOX_STAGE1_ALREADY_RUNNING"; exit 0
fi
PID="$LOG/NOX_STAGE1.pid"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
 cmd="$(ps -p "$(cat "$PID")" -o args= || true)"
 if [[ "$cmd" == *run_new_a5000_9b_autonomous.sh* ]]; then
   echo "NOX_STAGE1_ALREADY_RUNNING_PID $(cat "$PID")"; exit 0
 fi
fi
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/474a3539c8b0691c456257898216991efd7ed81d/nox_runpod/stage0/run_new_a5000_9b_autonomous.sh'
curl -fLsS --retry 4 "$URL" -o "$TOOLS/run_new_a5000_9b_autonomous.sh.new"
bash -n "$TOOLS/run_new_a5000_9b_autonomous.sh.new"
mv -f "$TOOLS/run_new_a5000_9b_autonomous.sh.new" "$TOOLS/run_new_a5000_9b_autonomous.sh"
chmod 700 "$TOOLS/run_new_a5000_9b_autonomous.sh"
# The first stage explicitly leaves GPU running for queued knowledge stage.
nohup setsid bash "$TOOLS/run_new_a5000_9b_autonomous.sh" </dev/null >>"$LOG/NOX_9B_AUTONOMOUS.log" 2>&1 &
pid=$!
echo "$pid" > "$PID"
sleep 3
if ! kill -0 "$pid" 2>/dev/null; then
 echo "STAGE1_START_FAILED"
 tail -n 25 "$LOG/NOX_9B_AUTONOMOUS.log"
 exit 18
fi
echo "NOX_STAGE1_DETACHED pid=$pid"
echo "NOX_STAGE2_QUEUE_INDEPENDENT; WINDOWS_CAN_DISCONNECT_IF_TRANSFERS_ARE_COMPLETE"
echo "LOG=$LOG/NOX_9B_AUTONOMOUS.log"
