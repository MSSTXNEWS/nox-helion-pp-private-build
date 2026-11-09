#!/usr/bin/env bash
# NOX parallel learning lane, independent of the primary 9B trainer.
set -Eeuo pipefail
ROOT=/workspace/nox
LOG="$ROOT/logs"
TOOLS="$ROOT/tools"
mkdir -p "$LOG" "$TOOLS"
SCRIPT="$TOOLS/nox_parallel_9b_lane.py"
PID="$LOG/nox_parallel_9b_lane.pid"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
  args="$(ps -p "$(cat "$PID")" -o args= || true)"
  if [[ "$args" == *nox_parallel_9b_lane.py* ]]; then
    echo "NOX_PARALLEL_ALREADY_RUNNING pid=$(cat "$PID")"
    exit 0
  fi
fi
# Strict lock for separate lane; never overwrite the primary 9B model.
exec 7>"$LOG/nox_parallel_9b_lane.lock"
if ! flock -n 7; then echo "NOX_PARALLEL_LOCKED"; exit 0; fi
test -s "$ROOT/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json" || { echo "HOLD_NO_9B";exit 21; }
test -s "$ROOT/embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json" || { echo "HOLD_NO_EMBRYO";exit 22; }
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace || { echo "HOLD_NO_PERSISTENCE";exit 23; }
PY="$ROOT/prime9b-venv/bin/python"
test -x "$PY" || { echo "HOLD_ENV_NOT_READY";exit 24; }
test -s "$TOOLS/nox_prime_9b.py" || { echo "HOLD_MAIN_TRAINER_NOT_READY";exit 25; }
if [ -s "$ROOT/checkpoints/NOX_9B_PARALLEL_TECH/pass1/SUCCESS.json" ]; then
 echo "NOX_PARALLEL_ALREADY_SAVED";exit 0
fi
URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/e525520b589e5c477972bbe553b264294d6de492/nox_runpod/stage0/nox_parallel_9b_lane.py"
curl -fLsS --retry 3 "$URL" -o "$SCRIPT.new"
"$PY" -m py_compile "$SCRIPT.new"
mv -f "$SCRIPT.new" "$SCRIPT"
# Explicitly separate session; allow Windows shutdown.
nohup setsid bash -c 'exec 8>/workspace/nox/logs/nox_parallel_9b_exec.lock; flock -n 8 || exit 0; exec /workspace/nox/prime9b-venv/bin/python -u /workspace/nox/tools/nox_parallel_9b_lane.py' </dev/null >>"$LOG/NOX_9B_PARALLEL.log" 2>&1 &
pid=$!
echo "$pid" > "$PID"
sleep 3
if ! kill -0 "$pid" 2>/dev/null; then
 echo "NOX_PARALLEL_START_FAILED"
 tail -n 15 "$LOG/NOX_9B_PARALLEL.log"
 exit 26
fi
echo "NOX_PARALLEL_DETACHED pid=$pid"
echo "PRIMARY_9B_UNTOUCHED; NO_GPU_STOP"
echo "LOG=$LOG/NOX_9B_PARALLEL.log"
