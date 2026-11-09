#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/workspace/nox
TOOLS="$ROOT/tools"
LOG="$ROOT/logs"
PID="$LOG/nox_embryo_unattended.pid"
OUT="$LOG/nox_embryo_unattended.log"
RUN_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/a9e25cc4b26bf8d4c1d2f8934b2e9b7abfbf0629/nox_runpod/stage0/run_embryo_training_autostop.sh"
SUP_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/e8cff9b91f04f74fc80f1480362cd4841b892030/nox_runpod/stage0/supervise_embryo.sh"
mkdir -p "$TOOLS" "$LOG"
test -s "$ROOT/embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json" || { echo "HOLD: Embryo absent"; exit 14; }
test -s "$ROOT/distillation/embryo_v1/9b_teacher_corpus.jsonl" || { echo "HOLD: teacher data absent"; exit 15; }
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
  echo "ALREADY_RUNNING pid=$(cat "$PID")"
  exit 0
fi
# Server fetches Linux files directly; never pass scripts through PowerShell CRLF.
curl -fLsS --retry 3 "$RUN_URL" -o "$TOOLS/run_embryo_training_autostop.sh.new"
curl -fLsS --retry 3 "$SUP_URL" -o "$TOOLS/supervise_embryo.sh.new"
bash -n "$TOOLS/run_embryo_training_autostop.sh.new"
bash -n "$TOOLS/supervise_embryo.sh.new"
mv -f "$TOOLS/run_embryo_training_autostop.sh.new" "$TOOLS/run_embryo_training_autostop.sh"
mv -f "$TOOLS/supervise_embryo.sh.new" "$TOOLS/supervise_embryo.sh"
chmod 700 "$TOOLS/run_embryo_training_autostop.sh" "$TOOLS/supervise_embryo.sh"
nohup setsid bash "$TOOLS/supervise_embryo.sh" </dev/null >>"$OUT" 2>&1 &
echo "$!" > "$PID"
sleep 3
if ! kill -0 "$(cat "$PID")" 2>/dev/null; then
  echo "LAUNCH_FAILED"; tail -n 15 "$OUT"; exit 18
fi
echo "NOX_SUPERVISOR_DETACHED pid=$(cat "$PID")"
echo "NOX_CHECKPOINTS=$ROOT/checkpoints/nox_genesis_stage0"
echo "WINDOWS_CAN_DISCONNECT; actual training only confirmed by step logs and checkpoint."
