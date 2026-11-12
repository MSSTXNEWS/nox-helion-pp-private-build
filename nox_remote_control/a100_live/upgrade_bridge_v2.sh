#!/usr/bin/env bash
# Upgrade ONLY the pre-existing NOX read-only bridge. Never stop trainers/NOX.
set -Eeuo pipefail
set +x
umask 077
BASE=/root/.local/nox-a100-live-bridge
FILE="$BASE/bridge.py"
HELPER="$BASE/train_actions.py"
PIDFILE="$BASE/agent.pid"
OLD_BLOB=df3117c3e2be533faa04e7a79a361c703cabffa2
NEW_BLOB=dd4dd914b6a7790d87816a38bb541a5e5dc75312
HELPER_BLOB=2d31f98e7a8ce648074e12e45c69ea7fc6d406e5
COMMIT=e267cd6511bebd9a136ea83b08e6b397690a053d
URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$COMMIT/nox_remote_control/a100_live"
mkdir -p "$BASE"
TMP=$(mktemp -d /tmp/nox-bridge-upgrade-XXXXXXXX)
trap 'rm -rf "$TMP"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$URL/bridge_v2.py" -o "$TMP/bridge.py"
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$URL/train_actions.py" -o "$TMP/train_actions.py"
python3 - "$TMP/bridge.py" "$NEW_BLOB" "$TMP/train_actions.py" "$HELPER_BLOB" <<'PY'
import sys,hashlib,py_compile
for path,expected in [(sys.argv[1],sys.argv[2]),(sys.argv[3],sys.argv[4])]:
    b=open(path,'rb').read()
    got=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    if got!=expected: raise SystemExit("HOLD_SOURCE_BLOB_MISMATCH")
    py_compile.compile(path,doraise=True)
print("VERIFIED_BRIDGE_AND_TRAINER_ACTIONS")
PY
# Stage source archive while old diagnostics bridge stays online.
PYTHONPATH="$TMP" python3 - <<'PY'
from train_actions import stage_fast75
out=stage_fast75()
print("FAST75_CODE_STAGE",out)
if out.get("state")!="READY": raise SystemExit("HOLD_TRAINER_SOURCE_STAGE")
PY
gitblob() {
 python3 - "$1" <<'PY'
import hashlib,sys
b=open(sys.argv[1],'rb').read()
print(hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest())
PY
}
if [ ! -f "$FILE" ] || [ ! -f "$PIDFILE" ];then echo "HOLD_OLD_BRIDGE_MISSING";exit 6;fi
BLOB=$(gitblob "$FILE")
case "$BLOB" in
  "$OLD_BLOB") ;;
  "$NEW_BLOB") echo "NOX_BRIDGE_V2_ALREADY_INSTALLED";exit 0 ;;
  *) echo "HOLD_OLD_BRIDGE_UNEXPECTED_HASH";exit 7 ;;
esac
PID=$(cat "$PIDFILE")
if [[ ! "$PID" =~ ^[0-9]+$ ]] || [ ! -f "/proc/$PID/cmdline" ];then echo "HOLD_OLD_BRIDGE_PID";exit 8;fi
ARGS=$(tr '\0' ' ' <"/proc/$PID/cmdline")
case "$ARGS" in
  *python*"$FILE"*) ;;
  *) echo "HOLD_BRIDGE_PID_MISMATCH";exit 9 ;;
esac
if [ -f "$HELPER" ] && ! cmp -s "$HELPER" "$TMP/train_actions.py";then
  echo "HOLD_EXISTING_TRAIN_HELPER_DIFFERENT";exit 10
fi
cp "$FILE" "$BASE/bridge.py.v1.saved"
# Change only the bridge, never trainer/watchdog. Graceful owner-specific termination.
kill -TERM "$PID"
for i in $(seq 1 10);do
  if ! kill -0 "$PID" 2>/dev/null;then break;fi
  sleep 1
done
if kill -0 "$PID" 2>/dev/null;then echo "HOLD_OLD_BRIDGE_NOT_EXITED";exit 11;fi
cp "$TMP/train_actions.py" "$HELPER"
cp "$TMP/bridge.py" "$BASE/bridge.py.new"
chmod 600 "$HELPER" "$BASE/bridge.py.new"
mv "$BASE/bridge.py.new" "$FILE"
nohup python3 -u "$FILE" >>"$BASE/agent.log" 2>&1 </dev/null &
NEWPID=$!
printf '%s\n' "$NEWPID" > "$PIDFILE"
sleep 3
if kill -0 "$NEWPID" 2>/dev/null;then
  echo "NOX_TRAIN_CONTROL_READY PID=$NEWPID"
  echo "NO_TRAINER_STOP_OR_RESET=TRUE"
  echo "NEXT_TASKS=stage_fast75,prepare_local,resume_training,training_status"
  exit 0
fi
echo "HOLD_BRIDGE_V2_START_FAILED_ROLLBACK"
cp "$BASE/bridge.py.v1.saved" "$FILE"
nohup python3 -u "$FILE" >>"$BASE/agent.log" 2>&1 </dev/null &
printf '%s\n' "$!" > "$PIDFILE"
exit 12
