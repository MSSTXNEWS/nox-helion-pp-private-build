#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/workspace/nox
DIR="$ROOT/tools"
LOG="$ROOT/logs"
PID="$LOG/nox_27b_teacher_download.pid"
mkdir -p "$DIR" "$LOG"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null;then
 cmd="$(ps -p "$(cat "$PID")" -o args= || true)"
 if [[ "$cmd" == *download_qwen38_27b_teacher.sh* ]];then
  echo "NOX_27B_DONOR_DOWNLOAD_ALREADY_RUNNING pid=$(cat "$PID")";exit 0
 fi
fi
curl -fLsS --retry 3 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/b86b62f668dbb392dc6adf18c5ec845a8f69c8b6/nox_runpod/stage0/download_qwen38_27b_teacher.sh' -o "$DIR/download_qwen38_27b_teacher.sh.new"
bash -n "$DIR/download_qwen38_27b_teacher.sh.new"
mv -f "$DIR/download_qwen38_27b_teacher.sh.new" "$DIR/download_qwen38_27b_teacher.sh"
chmod 700 "$DIR/download_qwen38_27b_teacher.sh"
nohup setsid bash "$DIR/download_qwen38_27b_teacher.sh" </dev/null >> "$LOG/NOX_27B_DONOR_DOWNLOAD.log" 2>&1 &
pid=$!
echo "$pid" > "$PID"
sleep 2
if ! kill -0 "$pid" 2>/dev/null;then
 echo "NOX_27B_DONOR_DOWNLOAD_FAILED_TO_START"
 tail -n 15 "$LOG/NOX_27B_DONOR_DOWNLOAD.log" || true
 exit 23
fi
echo "NOX_27B_DONOR_DOWNLOAD_DETACHED pid=$pid"
echo "NOX_GPU_9B_TRAINING_UNTOUCHED"
echo "WINDOWS_CAN_DISCONNECT"
