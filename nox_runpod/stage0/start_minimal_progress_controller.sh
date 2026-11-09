#!/usr/bin/env bash
# Minimal NOX absorption monitor; no GPU compute added, only 60 sec status.
set -Eeuo pipefail
NODE="$1"
case "$NODE" in A5000|A40);;*)echo HOLD_UNKNOWN_NODE;exit 2;;esac
R=/workspace/nox
C="$R/dispatcher/absorption_control"
mkdir -p "$C" "$R/logs" "$R/tools"
GPU="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
[[ "$GPU" == *"$NODE"* ]] || { echo "HOLD_WRONG_GPU $GPU";exit 3; }
exec 9>"$C/setup_$NODE.lock"
flock -n 9 || { echo NOX_PROGRESS_SETUP_ALREADY_RUNNING;exit 0; }
SRC="$R/tools/nox_absorption_progress_control_$NODE.py"
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/27d884cd59525dcf20baf641744d88ce052b1f6d/nox_runpod/stage0/nox_absorption_progress_control.py'
curl -fLsS --retry 3 "$URL" -o "$SRC.new"
python3 -m py_compile "$SRC.new"
mv -f "$SRC.new" "$SRC"
PID="$C/$NODE.pid"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null;then
 cmd="$(ps -p "$(cat "$PID")" -o args= || true)"
 if [[ "$cmd" == *"nox_progress_$NODE.sh"* ]];then
  echo "NOX_PROGRESS_ALREADY_RUNNING node=$NODE pid=$(cat "$PID")"
  exit 0
 fi
 echo HOLD_UNEXPECTED_PID_OWNER;exit 4
fi
RUN="$C/nox_progress_$NODE.sh"
cat > "$RUN" <<SUP
#!/usr/bin/env bash
set -Eeuo pipefail
exec 8>"$C/$NODE.supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$C/STOP_$NODE" ];do
 python3 -u "$SRC" --node "$NODE" >> "$R/logs/NOX_ABSORPTION_PROGRESS_$NODE.log" 2>&1 || true
 sleep 15
done
SUP
chmod 700 "$RUN"
nohup setsid bash "$RUN" </dev/null >>"$R/logs/NOX_PROGRESS_$NODE"_SUPERVISOR.log 2>&1 &
p=$!;echo "$p" >"$PID"
sleep 2
kill -0 "$p" 2>/dev/null || { echo HOLD_SUPERVISOR_FAILED;exit 5; }
echo "NOX_PROGRESS_MONITOR_STARTED node=$NODE pid=$p"
echo "STATUS=$C/$NODE"_status.json
echo "ONE_STATUS_PER_60SEC; NO_ADAPTERS; NO_GPU_MODEL_LOADS; NO_CHECKPOINT_OVERWRITES"
