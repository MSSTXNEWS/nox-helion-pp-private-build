#!/usr/bin/env bash
# A40: independent CUDA teacher stream + read-only 3-teacher S03 memory aggregation.
# Leaves existing CUDA distillation and A5000 NOX intact. NO adapters.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_accelerator"
L="$R/logs"
mkdir -p "$S" "$L" "$R/tools"
test -s "$R/tools/nox_prime_9b.py" && test -s "$R/models/NOX_PRIME_9B_INHERITED/config.json" || { echo "HOLD_NO_EXISTING_TEACHER"; exit 22; }
test -x "$R/prime9b-venv/bin/python" || { echo "HOLD_NO_PYTORCH_ENV"; exit 23; }
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A40* ]] || { echo "HOLD_GPU_NOT_A40"; exit 24; }
exec 9>"$S/start.lock"; flock -n 9 || { echo "NOX_ACCELERATOR_ALREADY_STARTING";exit 0; }
SECONDARY_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/c15e52c939feee847a2079def0d0b1080b748319/nox_runpod/stage0/a40_cuda_secondary_memory.py"
MEMORY_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/bf3c5dfacbd5bdb9aae66a69cbb251d126171aed/nox_runpod/stage0/a40_memory_neural_integrator.py"
curl --fail --location --silent --show-error --retry 4 "$SECONDARY_URL" -o "$R/tools/a40_cuda_secondary_memory.py.new"
curl --fail --location --silent --show-error --retry 4 "$MEMORY_URL" -o "$R/tools/a40_memory_neural_integrator.py.new"
"$R/prime9b-venv/bin/python" -m py_compile "$R/tools/a40_cuda_secondary_memory.py.new" "$R/tools/a40_memory_neural_integrator.py.new"
mv "$R/tools/a40_cuda_secondary_memory.py.new" "$R/tools/a40_cuda_secondary_memory.py"
mv "$R/tools/a40_memory_neural_integrator.py.new" "$R/tools/a40_memory_neural_integrator.py"
cat > "$S/second_cuda_supervisor.sh" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_accelerator"
exec 8>"$S/second_cuda.lock";flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')
  hot=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1 | tr -d ' ')
  if [ "$free" -ge 12500 ] && [ "$hot" -lt 75 ];then
    "$R/prime9b-venv/bin/python" -u "$R/tools/a40_cuda_secondary_memory.py" >>"$R/logs/NOX_A40_SECONDARY_CUDA.log" 2>&1 || true
  else
    printf '%s secondary hold VRAM_free=%s temp=%s\n' "$(date -u +%FT%TZ)" "$free" "$hot" >>"$R/logs/NOX_A40_SECONDARY_CUDA.log"
  fi
  sleep 60
done
BASH
cat > "$S/three_teacher_memory_supervisor.sh" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_accelerator"
exec 8>"$S/memory.lock";flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
  /usr/bin/python3 -u "$R/tools/a40_memory_neural_integrator.py" --role memory >>"$R/logs/NOX_THREE_TEACHER_MEMORY.log" 2>&1 || true
  sleep 60
done
BASH
chmod 700 "$S/second_cuda_supervisor.sh" "$S/three_teacher_memory_supervisor.sh"
for role in second_cuda three_teacher_memory;do
 pidfile="$S/${role}.pid"
 if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null;then
   echo "NOX_${role}_ALREADY_RUNNING pid=$(cat "$pidfile")"
 else
   nohup setsid bash "$S/${role}_supervisor.sh" </dev/null >>"$L/NOX_A40_ACCELERATOR_SUPERVISOR.log" 2>&1 &
   echo "$!" > "$pidfile"
   echo "NOX_${role}_SUPERVISOR_REQUESTED pid=$(cat "$pidfile")"
 fi
done
echo "NOX_A40_ACCELERATOR_LAUNCHED"
echo "CHECK_CUDA_LOG=$L/NOX_A40_SECONDARY_CUDA.log"
echo "CHECK_MEMORY_LOG=$L/NOX_THREE_TEACHER_MEMORY.log"
echo "PRESERVE_EXISTING_DISTILLATION_AND_WEIGHTS"
