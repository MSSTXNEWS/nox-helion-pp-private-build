#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_legacy_full_weight_rescue"
mkdir -p "$S" "$R/logs" "$R/tools"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader|head -1)" == *A5000* ]] || { echo HOLD_WRONG_GPU;exit 2; }
exec 9>"$S/launch.lock"
flock -n 9 || { echo ALREADY_LAUNCHING;exit 0; }
u='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/a1bf898cafff13402398cda2b6a8f67123dba843/nox_runpod/stage0/a5000_rescue_legacy_full_weights.py'
curl -fsSL --retry 3 "$u" -o "$R/tools/a5000_rescue_legacy_full_weights.py.new"
PY="$R/prime9b-venv/bin/python"
test -x "$PY" || { echo HOLD_NO_VENV;exit 3; }
"$PY" -m py_compile "$R/tools/a5000_rescue_legacy_full_weights.py.new"
mv "$R/tools/a5000_rescue_legacy_full_weights.py.new" "$R/tools/a5000_rescue_legacy_full_weights.py"
if [ -s "$S/worker.pid" ] && kill -0 "$(cat "$S/worker.pid")" 2>/dev/null;then
 echo "NOX_A5000_HISTORICAL_RESCUE_ALREADY_RUNNING pid=$(cat "$S/worker.pid")";exit 0
fi
nohup setsid "$PY" -u "$R/tools/a5000_rescue_legacy_full_weights.py" </dev/null >>"$R/logs/NOX_A5000_LEGACY_FULL_RESCUE.log" 2>&1 &
pid=$!;echo "$pid" > "$S/worker.pid"
echo "NOX_A5000_HISTORICAL_FULL_WEIGHT_RESCUE_REQUESTED pid=$pid"
echo "NOX_ACTIVE_TRAINING_UNTOUCHED; NO_ADAPTER_TRAINING"
echo "MODEL_OUTPUT=/opt/nox_historical_full_weights (EPHEMERAL UNTIL BACKED UP)"
echo "LOG=$R/logs/NOX_A5000_LEGACY_FULL_RESCUE.log"
