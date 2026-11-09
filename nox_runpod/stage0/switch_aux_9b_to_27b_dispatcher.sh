#!/usr/bin/env bash
# NOX resource switch: gracefully retire auxiliary 9B and stage verified Qwen3.5-27B donor.
# Never kill primary NOX, delete its weights, or spawn competing large GPU teachers.
set -Eeuo pipefail
ROOT=/workspace/nox
LOG="$ROOT/logs"
AUX="$ROOT/checkpoints/NOX_9B_PARALLEL_TECH"
TEACHER="$ROOT/teachers/Qwen3.8-27B"
SCRIPT="$ROOT/tools/download_qwen38_27b_teacher.sh"
PID="$LOG/nox_27b_dispatcher.pid"
mkdir -p "$LOG" "$AUX" "$ROOT/tools"
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo HOLD_NO_PERSISTENT_VOLUME; exit 11; }
# The auxiliary 9B loop checks this before every pass. No interruption or loss of checkpoints.
touch "$AUX/STOP_AFTER_CURRENT_PASS"
echo "NOX_AUX_9B_GRACEFUL_STOP_REQUESTED_CURRENT_PASS_WILL_FINISH"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
 echo "NOX_27B_DISPATCHER_ALREADY_RUNNING pid=$(cat "$PID")"
 exit 0
fi
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/195f803489628aa237c14baa9172989189f3ef14/nox_runpod/stage0/download_qwen38_27b_teacher.sh'
curl -fLsS --retry 3 "$URL" -o "$SCRIPT.new"
bash -n "$SCRIPT.new"
mv -f "$SCRIPT.new" "$SCRIPT"
chmod 700 "$SCRIPT"
# CPU-side async downloader uses a separate lock; safe to run while NOX 9B trains,
# provided storage guard allows it. 27B GPU inference is deferred.
nohup setsid bash -c '
set -Eeuo pipefail
ROOT=/workspace/nox
LOG="$ROOT/logs"
AUX="$ROOT/checkpoints/NOX_9B_PARALLEL_TECH"
exec 7>"$LOG/nox_27b_switch.lock"
flock -n 7 || exit 0
deadline=$(( $(date +%s)+14400 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
 if [ -e "$AUX/parallel_result.json" ]; then break;fi
 active=$(pgrep -f "[p]ython.*nox_parallel_9b_lane.py" || true)
 if [ -z "$active" ]; then break; fi
 sleep 15
done
echo "NOX_SECONDARY_9B_SWITCHED_OFF_AFTER_CHECKPOINT" >>"$LOG/NOX_27B_DISPATCHER.log"
bash "$ROOT/tools/download_qwen38_27b_teacher.sh" >>"$LOG/NOX_27B_DISPATCHER.log" 2>&1 || { echo "NOX_27B_DOWNLOAD_HOLD_OR_FAILED" >>"$LOG/NOX_27B_DISPATCHER.log"; exit 0; }
echo "NOX_27B_DONOR_DOWNLOADED_INFERENCE_WAITING_FOR_FREE_GPU" >>"$LOG/NOX_27B_DISPATCHER.log"
' </dev/null >>"$LOG/NOX_27B_DISPATCHER.log" 2>&1 &
echo $! > "$PID"
echo "NOX_27B_DISPATCHER_DETACHED pid=$(cat "$PID")"
echo "PRIMARY_NOX_9B_UNTOUCHED"
echo "DONOR_27B_INFERENCE_NOT_STARTED_WHILE_PRIMARY_GPU_BUSY"
