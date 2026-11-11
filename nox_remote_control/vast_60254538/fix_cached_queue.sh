#!/usr/bin/env bash
# Hotfix only the isolated NOX read-only observer. Does not touch learner.py.
set -Eeuo pipefail
umask 077
DIR=/root/nox/remote_control/vast_60254538
SRC=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/4432ba75d32cb4b934d080cd70a2a48d645c8643/nox_remote_control/vast_60254538/vast_readonly_dispatcher.py
EXPECTED=ae9e64787bc3e6757bfbb4e4f910a21d963455c4
mkdir -p "$DIR"
TMP=$(mktemp "$DIR/.observer_next.XXXXXXXX")
trap 'rm -f "$TMP"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$SRC" -o "$TMP"
ACTUAL=$(python3 - "$TMP" <<'PY'
import hashlib,sys
b=open(sys.argv[1],'rb').read()
print(hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest())
PY
)
test "$ACTUAL" = "$EXPECTED" || { echo "HOLD_HASH_MISMATCH"; exit 4; }
python3 -m py_compile "$TMP"
DEST="$DIR/vast_readonly_dispatcher.py"
if test -f "$DEST" && ! cmp -s "$TMP" "$DEST"; then
  cp -p "$DEST" "$DIR/vast_readonly_dispatcher.py.before_api_fix"
fi
PID=""
if test -f "$DIR/agent.pid"; then PID=$(cat "$DIR/agent.pid"); fi
if [[ "$PID" =~ ^[0-9]+$ ]] && test -f "/proc/$PID/cmdline"; then
  ARGS=$(tr '\0' ' ' < "/proc/$PID/cmdline")
  case "$ARGS" in
    *python*"$DEST"*)
      kill -TERM "$PID"
      for i in 1 2 3 4 5 6 7 8 9 10; do
        if ! kill -0 "$PID" 2>/dev/null; then break; fi
        sleep 1
      done
      if kill -0 "$PID" 2>/dev/null; then
        echo "HOLD_OBSERVER_STILL_ACTIVE"; exit 5
      fi
      ;;
    *) echo "HOLD_PID_OWNER_MISMATCH"; exit 6 ;;
  esac
fi
install -m 0600 "$TMP" "$DEST"
nohup python3 -u "$DEST" >> "$DIR/agent.log" 2>&1 </dev/null &
PID=$!
printf '%s\n' "$PID" > "$DIR/agent.pid"
sleep 3
if kill -0 "$PID" 2>/dev/null; then
  echo "OBSERVER_API_FIXED_PID=$PID"
  ls -lh "$DIR"/receipt_*.json 2>/dev/null || echo "NO_RECEIPTS_YET"
  cat "$DIR/last_error.json" 2>/dev/null || true
else
  echo "HOLD_OBSERVER_RESTART_FAILED"; tail -n 20 "$DIR/agent.log"; exit 7
fi
