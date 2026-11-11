#!/usr/bin/env bash
# Installs an isolated read-only observer; NEVER sends STOP or edits NOX training.
set -Eeuo pipefail
umask 077
ROOT=/root/nox/remote_control/vast_60232647
mkdir -p "$ROOT"
PIN=ae760aa8b1a9193c4030638f48acaaca874bd8e0
SRC=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/ae760aa8b1a9193c4030638f48acaaca874bd8e0/nox_remote_control/vast_60232647/vast_readonly_dispatcher.py
BLOB=e3659fdfb1f685d41dab15c4b6813a3bd3a35093
TMP=$(mktemp "$ROOT/.download.XXXXXXXX")
trap 'rm -f "$TMP"' EXIT
curl --proto '=https' --tlsv1.2 -fLsS --retry 3 "$SRC" -o "$TMP"
GOT=$(python3 - "$TMP" <<'PY'
import sys,hashlib
d=open(sys.argv[1],'rb').read()
print(hashlib.sha1(b'blob '+str(len(d)).encode()+b'\0'+d).hexdigest())
PY
)
if [[ "$GOT" != "$BLOB" ]]; then echo "HOLD: source digest mismatch"; exit 4; fi
python3 -m py_compile "$TMP"
FILE="$ROOT/vast_readonly_dispatcher.py"
if [[ -f "$FILE" ]] && ! cmp -s "$TMP" "$FILE"; then
  echo "HOLD: existing dispatcher differs, nothing overwritten"
  exit 5
fi
if [[ ! -f "$FILE" ]]; then install -m 0600 "$TMP" "$FILE"; fi
if [[ -f "$ROOT/agent.pid" ]]; then
  PID=$(cat "$ROOT/agent.pid")
  if [[ "$PID" =~ ^[0-9]+$ ]] && [[ -e "/proc/$PID/cmdline" ]] && tr '\0' ' ' < "/proc/$PID/cmdline" | grep -Fq "$FILE"; then
    echo "NOX_VAST_OBSERVER_ALREADY_RUNNING PID=$PID"; exit 0
  fi
fi
nohup python3 -u "$FILE" >> "$ROOT/agent.log" 2>&1 </dev/null &
PID=$!
echo "$PID" > "$ROOT/agent.pid"
sleep 2
if kill -0 "$PID" 2>/dev/null; then
  echo "NOX_VAST_OBSERVER_STARTED PID=$PID"
  echo "Local receipts: $ROOT/receipt_*.json"
  echo "Remote receipts are disabled (GitHub repository is public)."
else
  echo "HOLD_START_FAILED"; tail -n 10 "$ROOT/agent.log"; exit 7
fi
