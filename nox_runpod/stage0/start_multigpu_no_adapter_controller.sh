#!/usr/bin/env bash
# Start selected NOX GPU-role controller and useful workloads, no adapter creation.
set -Eeuo pipefail
ROLE="${1:?A5000 or A40}"
case "$ROLE" in A40|A5000);;*) echo HOLD_INVALID_ROLE;exit 2;;esac
R=/workspace/nox
S="$R/dispatcher/NOX_MULTI_GPU"
LOG="$R/logs"
mkdir -p "$S" "$LOG" "$R/tools"
[ "$(df -P /workspace | tail -1 | awk '{print $6}')" = /workspace ] || { echo HOLD_MISSING_SHARED_VOLUME;exit 3; }
GPU="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
[[ "$GPU" == *"$ROLE"* ]] || { echo "HOLD_GPU_MISMATCH gpu=$GPU role=$ROLE";exit 4; }
SRC='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/5cd3a2b86f56e1562e6e1ebe93b527e03ab5344b/nox_runpod/stage0/nox_no_adapter_multigpu_controller.py'
curl -fLsS --retry 3 "$SRC" -o "$R/tools/nox_no_adapter_multigpu_controller.py.new"
python3 -m py_compile "$R/tools/nox_no_adapter_multigpu_controller.py.new"
mv -f "$R/tools/nox_no_adapter_multigpu_controller.py.new" "$R/tools/nox_no_adapter_multigpu_controller.py"
if [ "$ROLE" = A40 ];then
  # This starts a real second CUDA teacher lane if enough VRAM and also S03 curator.
  BOOST='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/7ea051ae3e6ae5dea51eecc184ac646d708c611b/nox_runpod/stage0/boost_a40_safe_two_cuda_and_memory.sh'
  echo NOX_A40_CUDA_BOOST_REQUEST
  curl -fLsS --retry 3 "$BOOST" | bash || echo NOX_A40_BOOST_HOLD_REVIEW_LOG
else
  DUAL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/e9fa4d36885089170c0534a66fc83862f2c1b0e5/nox_runpod/stage0/start_a5000_two_pure_cuda_streams.sh'
  echo NOX_A5000_DUAL_PURE_CUDA_REQUEST
  curl -fLsS --retry 3 "$DUAL" | bash || echo NOX_A5000_DUAL_CUDA_HOLD_CHECK_LEGACY_TRAINER_OR_RESOURCES
fi
SUP="$S/supervisor_${ROLE}.sh"
cat > "$SUP" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S=\$R/dispatcher/NOX_MULTI_GPU
exec 8>\$S/supervisor_${ROLE}.lock
flock -n 8 || exit 0
while [ ! -e \$S/STOP ];do
 python3 -u \$R/tools/nox_no_adapter_multigpu_controller.py --role $ROLE >>\$R/logs/NOX_${ROLE}_RESOURCE_CONTROLLER.log 2>&1 || true
 sleep 45
done
EOF
chmod 700 "$SUP"
PID="$S/supervisor_${ROLE}.pid"
if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null;then
 echo "NOX_${ROLE}_CONTROLLER_ALREADY_RUNNING pid=$(cat "$PID")"
else
 nohup setsid bash "$SUP" </dev/null >>"$LOG/NOX_${ROLE}_CONTROLLER_SUPERVISOR.log" 2>&1 &
 echo $! > "$PID"
 echo "NOX_${ROLE}_CONTROLLER_DETACHED pid=$(cat "$PID")"
fi
echo "NOX_${ROLE}_SLOTS_CONFIGURED=$([ "$ROLE" = A40 ] && echo 4 || echo 2)"
echo "NO_ADAPTER_TRAINING; CHECK_REAL_STATUS=$S/${ROLE}_snapshot.json"
