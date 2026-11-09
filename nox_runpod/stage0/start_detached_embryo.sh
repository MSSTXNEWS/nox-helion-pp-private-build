#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/workspace/nox
RUN="$ROOT/tools/run_embryo_training_autostop.sh"
LOG="$ROOT/logs/nox_embryo_unattended.log"
PID="$ROOT/logs/nox_embryo_unattended.pid"
STATUS="$ROOT/logs/nox_embryo_unattended.status"
mkdir -p "$ROOT/tools" "$ROOT/logs" "$ROOT/checkpoints"
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo 'HOLD: /workspace is not mounted'; exit 11; }
command -v runpodctl >/dev/null || { echo 'HOLD: runpodctl missing'; exit 12; }
runpodctl pod get rsjmb616w0tqio >/dev/null 2>&1 || { echo 'HOLD: RunPod API not authenticated, cannot auto-stop'; exit 13; }
test -s "$ROOT/distillation/embryo_v1/9b_teacher_corpus.jsonl" || { echo 'HOLD: teacher corpus missing'; exit 14; }
test -s "$ROOT/embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json" || { echo 'HOLD: original Embryo missing'; exit 15; }
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then echo "ALREADY_RUNNING_PID $(cat "$PID")"; exit 0; fi
curl -fsSL --retry 3 --connect-timeout 15 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/d584054ed3a7aca41abc80b6ed53912250f60536/nox_runpod/stage0/run_embryo_training_autostop.sh' -o "$RUN.new"
bash -n "$RUN.new"
mv -f "$RUN.new" "$RUN"
chmod 700 "$RUN"
echo "LAUNCHING" > "$STATUS"
nohup setsid bash "$RUN" </dev/null >>"$LOG" 2>&1 &
echo $! > "$PID"
sleep 3
if ! kill -0 "$(cat "$PID")" 2>/dev/null; then echo "LAUNCH_FAILED"; tail -n 25 "$LOG"; exit 16; fi
# Independent deadline guard: stop compute no later than 4h even if learner is stuck.
WATCH="$ROOT/logs/nox_embryo_watchdog.pid"
if [ ! -f "$WATCH" ] || ! kill -0 "$(cat "$WATCH")" 2>/dev/null; then
  nohup setsid bash -c 'sleep 14460; runpodctl pod stop rsjmb616w0tqio' </dev/null >>"$ROOT/logs/nox_embryo_watchdog.log" 2>&1 &
  echo $! > "$WATCH"
fi
echo "DETACHED_TRAINING_PROCESS_STARTED pid=$(cat "$PID")"
echo "LOG=$LOG"
echo "IMPORTANT: Detached process may fail later. Only receipt proves training. If stop API fails, manually stop pod."
