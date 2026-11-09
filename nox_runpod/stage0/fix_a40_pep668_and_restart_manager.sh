#!/usr/bin/env bash
# Fix PEP-668 failure on A40 without changing shared NOX weights/checkpoints.
set -Eeuo pipefail
ROOT=/workspace/nox
STATE="$ROOT/dispatcher/a40"
LOG="$ROOT/logs"
VENV=/opt/nox_a40_dispatcher_venv
mkdir -p "$STATE" "$LOG"
test -s "$STATE/manager.py" || { echo "HOLD_NO_A40_MANAGER_SOURCE"; exit 21; }
test "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | xargs)" = "NVIDIA A40" || { echo "HOLD_NOT_A40"; exit 22; }
# Venv is on the 50GB container disk. No system python pip modifications.
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --no-cache-dir --upgrade "huggingface_hub>=0.35,<2" >>"$LOG/NOX_A40_DEPENDENCY_SETUP.log" 2>&1
"$VENV/bin/python" - <<'PY'
import huggingface_hub,sys
print("NOX_A40_VENV_READY",sys.executable,huggingface_hub.__version__,flush=True)
PY
"$VENV/bin/python" -m py_compile "$STATE/manager.py" "$ROOT/tools/a40_three_teachers_worker.py"
# The old launcher continually restarts the failed system-python manager.
if [ -s "$STATE/manager.pid" ]; then
  old="$(cat "$STATE/manager.pid")"
  case "$old" in ''|*[!0-9]*) echo "HOLD_INVALID_OLD_MANAGER_PID"; exit 23;; esac
  if kill -0 "$old" 2>/dev/null; then
    cmd="$(ps -p "$old" -o args= || true)"
    if [[ "$cmd" == *"/workspace/nox/dispatcher/a40/manager.py"* ]]; then
      kill "$old" || true
      echo "NOX_A40_OBSOLETE_SUPERVISOR_STOPPED pid=$old"
    else
      echo "HOLD_MANAGER_PID_NOT_IDENTIFIED: $cmd"; exit 24
    fi
  fi
fi
# One manager only. A failed process resumes after 60 sec; manager locks will be added separately.
SUP="$STATE/supervisor_venv.sh"
cat > "$SUP" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
S=/workspace/nox/dispatcher/a40
L=/workspace/nox/logs
exec 8>"$S/supervisor_venv.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ]; do
  /opt/nox_a40_dispatcher_venv/bin/python -u "$S/manager.py" >> "$L/NOX_A40_MANAGER.log" 2>&1 || echo "$(date -u +%FT%TZ) manager exited with error" >> "$L/NOX_A40_SUPERVISOR.log"
  sleep 60
done
BASH
chmod 700 "$SUP"
nohup setsid bash "$SUP" </dev/null >>"$LOG/NOX_A40_SUPERVISOR.log" 2>&1 &
pid=$!
echo "$pid" > "$STATE/manager.pid"
sleep 3
if ! kill -0 "$pid" 2>/dev/null; then
 echo "HOLD_MANAGER_SUPERVISOR_EARLY_EXIT"
 tail -n 30 "$LOG/NOX_A40_SUPERVISOR.log"
 exit 25
fi
echo "NOX_A40_MANAGER_RESTARTED_WITH_VENV pid=$pid"
echo "NOX_A40_NOX_WEIGHTS_UNTOUCHED"
echo "NOX_A40_STATUS=$STATE/snapshot.json"
