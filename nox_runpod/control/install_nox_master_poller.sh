#!/usr/bin/env bash
# NOX two-Pod controller installer. Does not remove models, checkpoints, or SQLite.
set -Eeuo pipefail
NODE="${1:-}"
case "$NODE" in A40|A5000) ;; *) echo 'USAGE: install_nox_master_poller.sh A40|A5000'; exit 2;; esac
R=/workspace/nox
D="$R/dispatcher/nox_master_control"
mkdir -p "$D" "$R/logs"
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox_runpod/control/nox_master_poller.py'
curl --fail --show-error --silent --location --retry 3 "$URL" -o "$D/nox_master_poller.py.tmp"
python3 -m py_compile "$D/nox_master_poller.py.tmp"
mv -f "$D/nox_master_poller.py.tmp" "$D/nox_master_poller.py"
# Preserve every prior controller before only removing exact old A40 watchdog cron entries.
if [ "$NODE" = A40 ] && command -v crontab >/dev/null 2>&1; then
  OLD="$(crontab -l 2>/dev/null || true)"
  if printf '%s\n' "$OLD" | grep -F '/workspace/nox/dispatcher/a40_direct/watchdog_supervise.sh' >/dev/null 2>&1; then
    BACKUP="$D/crontab_before_nox_$(date -u +%Y%m%dT%H%M%SZ).txt"
    printf '%s\n' "$OLD" > "$BACKUP"
    printf '%s\n' "$OLD" | awk '!/^[[:space:]]*[^#].*\/workspace\/nox\/dispatcher\/a40_direct\/watchdog_supervise.sh/' | crontab -
    echo "LEGACY_A40_WATCHDOG_CRON_DISABLED BACKUP=$BACKUP"
  fi
fi
if [ "$NODE" = A40 ]; then
  # Existing CUDA teacher is asked to finish its in-flight example.
  mkdir -p "$R/dispatcher/a40_direct"
  touch "$R/dispatcher/a40_direct/STOP"
  # Exact watchdog only; let the current teacher finish/exit on STOP.
  python3 - <<'PY'
import pathlib, os, signal
target="/workspace/nox/dispatcher/a40_direct/watchdog_supervise.sh"
for p in pathlib.Path("/proc").iterdir():
    if not p.name.isdigit():
        continue
    try:
        args=[a.decode(errors="replace") for a in (p/"cmdline").read_bytes().split(bytes([0])) if a]
        if target in args:
            print("LEGACY_A40_WATCHDOG_SIGTERM", p.name, flush=True)
            os.kill(int(p.name), signal.SIGTERM)
    except (OSError, ValueError):
        pass
PY
fi
if [ -f "$D/poller_${NODE}.pid" ]; then
  PID="$(cat "$D/poller_${NODE}.pid" 2>/dev/null || true)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    ARGS="$(ps -p "$PID" -o args= || true)"
    if [[ "$ARGS" == *nox_master_poller.py* && "$ARGS" == *--node*"$NODE"* ]]; then
      echo "NOX_MASTER_POLLER_ALREADY_RUNNING PID=$PID NODE=$NODE"
      exit 0
    fi
  fi
fi
nohup python3 -u "$D/nox_master_poller.py" --node "$NODE" \
  >> "$R/logs/NOX_MASTER_CONTROL_${NODE}.log" 2>&1 </dev/null &
PID=$!
echo "$PID" > "$D/poller_${NODE}.pid"
sleep 3
if kill -0 "$PID" 2>/dev/null; then
  echo "NOX_MASTER_POLLER_RUNNING NODE=$NODE PID=$PID POLL_SECONDS=180"
else
  tail -n 25 "$R/logs/NOX_MASTER_CONTROL_${NODE}.log"
  echo "NOX_MASTER_POLLER_START_FAILED"
  exit 3
fi
