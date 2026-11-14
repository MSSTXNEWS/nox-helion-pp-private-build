#!/usr/bin/env bash
# Attach NOX A100 to ChatGPT via existing GitHub connection and private RunPod logs.
# No model/trainer restart, no shell execution from queue, no secrets.
set -Eeuo pipefail
set +x
umask 077
DEST=/root/.local/nox-a100-live-bridge
FILE="$DEST/bridge.py"
PIDFILE="$DEST/agent.pid"
URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/69d189279557a62ec1f2a15dc47f63aa2adc0d00/nox_remote_control/a100_live/bridge.py"
EXPECTED="df3117c3e2be533faa04e7a79a361c703cabffa2"
mkdir -p "$DEST"
TMP=$(mktemp /tmp/nox-a100-bridge-XXXXXXXX)
trap 'rm -f "$TMP"' EXIT
curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location --retry 3 "$URL" -o "$TMP"
ACTUAL=$(python3 - "$TMP" <<'PY'
import hashlib,sys
blob=open(sys.argv[1],"rb").read()
print(hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest())
PY
)
if [ "$ACTUAL" != "$EXPECTED" ]; then echo HOLD_CODE_HASH; exit 3; fi
python3 -m py_compile "$TMP"
if [ -e "$FILE" ] && ! cmp -s "$TMP" "$FILE"; then
  echo HOLD_EXISTING_BRIDGE_DIFFERENT
  exit 4
fi
if [ ! -e "$FILE" ]; then cp "$TMP" "$FILE"; chmod 600 "$FILE"; fi
if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE")
  if [[ "$PID" =~ ^[0-9]+$ ]] && [ -e "/proc/$PID/cmdline" ]; then
    COMMAND=$(tr '\0' ' ' < "/proc/$PID/cmdline")
    if [[ "$COMMAND" == *"$FILE"* ]]; then
      echo "NOX_A100_BRIDGE_ALREADY_RUNNING PID=$PID"
      exit 0
    fi
  fi
fi
# Test the out-of-band return path before claiming that ChatGPT can read it.
if ! printf 'NOX_BRIDGE_BOOTSTRAP runpod-5f3j8hwyicc0bp protocol=v1\n' >/proc/1/fd/1; then
  echo HOLD_CONTAINER_LOG_RETURN
  exit 5
fi
nohup python3 -u "$FILE" >>"$DEST/agent.log" 2>&1 </dev/null &
PID=$!
printf '%s\n' "$PID" > "$PIDFILE"
sleep 2
if kill -0 "$PID" 2>/dev/null; then
  echo "NOX_A100_BRIDGE_RUNNING PID=$PID"
  echo "NO_TRAINING_CHANGES=TRUE"
  echo "READ_ONLY_OPERATIONS=gpu,disk,processes,checkpoint,preflight,health"
else
  echo HOLD_BRIDGE_START_FAILED
  tail -n 10 "$DEST/agent.log"
  exit 6
fi
