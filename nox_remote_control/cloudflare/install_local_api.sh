#!/usr/bin/env bash
# NOX Control API local installer: no trainer/STOP/network volume changes.
set -Eeuo pipefail
set +x
umask 077
NODE="$1"
case "$NODE" in
  runpod-5f3j8hwyicc0bp|vast-60254538) ;;
  *) echo "USAGE: bash install_local_api.sh <node>"; exit 2 ;;
esac
BASE=/root/.local/nox-control-cloudflare
mkdir -p "$BASE"
SRC="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/7f6182f14c076f324cba7c7f15b4f8f46bc1c4bd/nox_remote_control/cloudflare/nox_readonly_api.py"
EXPECTED="51243f7ee68120521f377a6ed2aad06aa2653f4e"
TMP=$(mktemp /tmp/nox-cloudflare-XXXXXXXX)
trap 'rm -f "$TMP"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$SRC" -o "$TMP"
ACTUAL=$(python3 - "$TMP" <<'PY'
import hashlib,sys
b=open(sys.argv[1],"rb").read()
print(hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest())
PY
)
if [ "$ACTUAL" != "$EXPECTED" ]; then echo HOLD_SOURCE_HASH_MISMATCH; exit 3; fi
python3 -m py_compile "$TMP"
DEST="$BASE/nox_readonly_api.py"
if [ -e "$DEST" ] && ! cmp -s "$TMP" "$DEST"; then
  echo "HOLD_EXISTING_API_DIFFERENT"; exit 4
fi
if [ ! -e "$DEST" ]; then cp "$TMP" "$DEST"; chmod 600 "$DEST"; fi
PIDFILE="$BASE/$NODE.pid"
if [ -f "$PIDFILE" ]; then
 PID=$(cat "$PIDFILE")
 if [[ "$PID" =~ ^[0-9]+$ ]] && [ -f "/proc/$PID/cmdline" ]; then
  ARGS=$(tr '\0' ' ' < "/proc/$PID/cmdline")
  if [[ "$ARGS" == *"$DEST"* ]]; then echo "NOX_CONTROL_API_ALREADY_RUNNING PID=$PID"; exit 0; fi
 fi
fi
if command -v ss >/dev/null 2>&1 && ss -ltn | grep -Eq '(^|[[:space:]])[^[:space:]]*:18796[[:space:]]'; then
 echo "HOLD_PORT_18796_IN_USE"; exit 5
fi
NOX_CONTROL_NODE="$NODE" nohup python3 -u "$DEST" >> "$BASE/$NODE.log" 2>&1 </dev/null &
PID=$!
printf '%s\n' "$PID" > "$PIDFILE"
sleep 1
if ! kill -0 "$PID" 2>/dev/null; then echo "HOLD_API_START_FAILED"; exit 6; fi
python3 - <<'PY'
import json,urllib.request
data=json.load(urllib.request.urlopen("http://127.0.0.1:18796/v1/health",timeout=5))
assert data["state"]=="READ_ONLY"
print("NOX_CONTROL_API_HEALTH_OK",data["node"])
PY
echo "LOCAL_API_READY: http://127.0.0.1:18796/v1/health"
echo "CLOUDFLARE_NOT_CONFIGURED; DO NOT PUBLISH BEFORE ACCESS POLICY"
