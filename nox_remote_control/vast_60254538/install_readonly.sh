#!/usr/bin/env bash
# NOX observer: new Vast instance 60254538. No training changes / no STOP.
set -Eeuo pipefail
umask 077
ROOT=/root/nox/remote_control/vast_60254538
mkdir -p "$ROOT"
URL=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/8398bc610dfeea24e25b1ef2e3ce87e1ddbe1821/nox_remote_control/vast_60254538/vast_readonly_dispatcher.py
EXPECTED=362ffd3ce61160d8e368c68dfb1de0bc637c05ef
TMP=$(mktemp "$ROOT/.download.XXXXXXXX")
trap 'rm -f "$TMP"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$URL" -o "$TMP"
ACTUAL=$(python3 - "$TMP" <<'PY'
import sys,hashlib
data=open(sys.argv[1],"rb").read()
print(hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest())
PY
)
if [ "$ACTUAL" != "$EXPECTED" ]; then echo "HOLD_SOURCE_MISMATCH"; exit 3; fi
python3 -m py_compile "$TMP"
TARGET="$ROOT/vast_readonly_dispatcher.py"
if [ -e "$TARGET" ] && ! cmp -s "$TMP" "$TARGET"; then echo "HOLD_EXISTING_FILE_DIFFERENT"; exit 4; fi
if [ ! -e "$TARGET" ]; then install -m 0600 "$TMP" "$TARGET"; fi
if [ -f "$ROOT/agent.pid" ]; then
 PID=$(cat "$ROOT/agent.pid")
 if [[ "$PID" =~ ^[0-9]+$ ]] && [ -f "/proc/$PID/cmdline" ] && tr '\0' ' ' < "/proc/$PID/cmdline" | grep -Fq "$TARGET"; then
   echo "OBSERVER_ALREADY_RUNNING PID=$PID"; exit 0
 fi
fi
nohup python3 -u "$TARGET" >> "$ROOT/agent.log" 2>&1 </dev/null &
PID=$!
printf '%s\n' "$PID" > "$ROOT/agent.pid"
sleep 2
if kill -0 "$PID" 2>/dev/null; then
 echo "OBSERVER_RUNNING PID=$PID"
 echo "LOCAL_RECEIPTS=$ROOT/receipt_*.json"
 echo "NO_TRAINING_CHANGE=TRUE"
else
 echo "HOLD_OBSERVER_FAILED"
 tail -n 12 "$ROOT/agent.log"
 exit 5
fi
