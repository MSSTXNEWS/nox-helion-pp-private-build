#!/usr/bin/env bash
# NOX RunPod A100 read-only GitHub task observer: isolated, does not touch running trainers.
set -Eeuo pipefail
umask 077
DIR=/workspace/nox/remote_control/runpod_5f3j8hwyicc0bp
mkdir -p "$DIR"
SOURCE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/04d27bc4620933c5e3ed30be14055ce275a90121/nox_remote_control/runpod_5f3j8hwyicc0bp/runpod_readonly_dispatcher.py
BLOB=c7a66720f465347072329894158d863e6abced09
TEMP=$(mktemp "$DIR/.fetch.XXXXXXXX")
trap 'rm -f "$TEMP"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$SOURCE" -o "$TEMP"
DIGEST=$(python3 - "$TEMP" <<'PY'
import hashlib,sys
data=open(sys.argv[1],"rb").read()
print(hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest())
PY
)
if [ "$DIGEST" != "$BLOB" ]; then echo "HOLD_SOURCE_SHA_MISMATCH"; exit 3; fi
python3 -m py_compile "$TEMP"
TARGET="$DIR/runpod_readonly_dispatcher.py"
if [ -e "$TARGET" ] && ! cmp -s "$TARGET" "$TEMP"; then echo "HOLD_EXISTING_OBSERVER_DIFFERENT"; exit 4; fi
if [ ! -e "$TARGET" ]; then install -m 0600 "$TEMP" "$TARGET"; fi
if [ -f "$DIR/agent.pid" ]; then
  PID=$(cat "$DIR/agent.pid")
  if [[ "$PID" =~ ^[0-9]+$ ]] && [ -e "/proc/$PID/cmdline" ]; then
    ARGS=$(tr '\0' ' ' < "/proc/$PID/cmdline")
    if [[ "$ARGS" == *"$TARGET"* ]]; then echo "OBSERVER_ALREADY_RUNNING PID=$PID"; exit 0; fi
  fi
fi
nohup python3 -u "$TARGET" >> "$DIR/agent.log" 2>&1 </dev/null &
PID=$!
printf '%s\n' "$PID" > "$DIR/agent.pid"
sleep 2
if kill -0 "$PID" 2>/dev/null; then
  echo "RUNPOD_NOX_OBSERVER_STARTED PID=$PID"
  echo "LOCAL_RECEIPTS=$DIR"
  echo "READ_ONLY=true"
else
  echo "HOLD_OBSERVER_START_FAILED"
  tail -n 15 "$DIR/agent.log"
  exit 5
fi
