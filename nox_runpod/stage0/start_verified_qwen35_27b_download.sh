#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox; mkdir -p "$R/tools" "$R/logs"
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/022a2b27fbbf9b2e979b105f627f55d603259e28/nox_runpod/stage0/download_qwen38_27b_teacher.sh'
SCRIPT="$R/tools/download_teacher_27b.sh"
PID="$R/logs/nox_teacher_27b.pid"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
  echo "NOX_27B_DOWNLOAD_ALREADY_RUNNING pid=$(cat "$PID")"; exit 0
fi
curl -fLsS --retry 3 "$URL" -o "$SCRIPT.new"
bash -n "$SCRIPT.new"
mv -f "$SCRIPT.new" "$SCRIPT"; chmod 700 "$SCRIPT"
nohup setsid bash "$SCRIPT" </dev/null >>"$R/logs/NOX_27B_DOWNLOAD.log" 2>&1 &
echo $! > "$PID"
sleep 2
if ! kill -0 "$(cat "$PID")" 2>/dev/null; then
 echo "NOX_27B_DOWNLOAD_EARLY_EXIT"; tail -n 14 "$R/logs/NOX_27B_DOWNLOAD.log"; exit 2
fi
echo "NOX_27B_DOWNLOAD_DETACHED pid=$(cat "$PID")"
echo "MODEL=Qwen3.5-27B-GGUF/Q4_K_M; GPU_TRAINING_NOT_INTERRUPTED"
