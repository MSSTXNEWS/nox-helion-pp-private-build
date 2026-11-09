#!/usr/bin/env bash
# Launch up to 2 productive NOX roles on A5000, 4 on A40, no adapters.
set -Eeuo pipefail
ROLE="${1:-}"
R=/workspace/nox
S="$R/dispatcher/dual_gpu"
mkdir -p "$S" "$R/tools" "$R/logs"
case "$ROLE" in A5000|A40) ;; *) echo "BAD_ROLE";exit 2;;esac
GPU="$(nvidia-smi --query-gpu=name --format=csv,noheader|head -1)"
[[ "$GPU" == *"$ROLE"* ]] || { echo "WRONG_GPU=$GPU";exit 3; }
exec 9>"$S/launch_$ROLE.lock"
flock -n 9 || { echo "LAUNCH_LOCKED";exit 0; }
PY="$R/prime9b-venv/bin/python"
test -x "$PY" || { echo "HOLD_NO_PYTORCH_VENV";exit 4; }
install_py(){
 local url="$1";local dest="$2"
 curl -fsSL --retry 4 "$url" -o "$dest.new"
 "$PY" -m py_compile "$dest.new"
 mv -f "$dest.new" "$dest"
}
start_supervisor(){
 local name="$1";local cmd="$2"
 local pidf="$S/${ROLE}_${name}.pid"
 if [ -s "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null;then
   echo "NOX_ROLE_EXISTING $ROLE $name pid=$(cat "$pidf")";return 0
 fi
 local runner="$S/${ROLE}_${name}.sh"
 cat >"$runner" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
exec 8>"$S/${ROLE}_${name}.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP_${ROLE}_${name}" ];do
  $cmd >> "$R/logs/NOX_${ROLE}_${name}.log" 2>&1 || true
  echo "\$(date -u +%FT%TZ) supervised_restart" >>"$R/logs/NOX_${ROLE}_${name}_RESTARTS.log"
  sleep 60
done
EOF
 chmod 700 "$runner"
 nohup setsid bash "$runner" </dev/null >>"$R/logs/NOX_${ROLE}_${name}_SUPERVISOR.log" 2>&1 &
 echo $! >"$pidf"
 echo "NOX_ROLE_STARTED $ROLE $name pid=$(cat "$pidf")"
}
# Process 1: already active CUDA teacher streaming; don't launch duplicate.
if [ "$ROLE" = A5000 ];then
 CUDA_SUP="$R/dispatcher/a5000_pure_distillation/supervisor.pid"
 CUDA_SCRIPT="$R/tools/a5000_pure_distillation.py"
 CUDA_LAUNCH='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/b610c67b3f28a39c4f7251e611e310df69b36189/nox_runpod/stage0/stop_legacy_qlora_start_pure_multipass_a5000.sh'
else
 CUDA_SUP="$R/dispatcher/a40_direct/supervisor.pid"
 CUDA_SCRIPT="$R/tools/a40_cuda_distillation_direct.py"
 CUDA_LAUNCH='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/798845ff6774c2dae1712693368dcfdd3ff8bcaa/nox_runpod/stage0/start_a40_cuda_distillation_direct.sh'
fi
if [ -s "$CUDA_SUP" ] && kill -0 "$(cat "$CUDA_SUP")" 2>/dev/null;then
 echo "NOX_ROLE_EXISTING $ROLE CUDA_PRIMARY pid=$(cat "$CUDA_SUP")"
else
 echo "NOX_CUDA_PRIMARY_RESTART_REQUESTED"
 curl -fsSL "$CUDA_LAUNCH" | bash
fi
# Process 2 on A5000: CPU-only source validation, no GPU RAM competition.
install_py 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/a1baecebcdac3484129306dcb51cf1012975a08f/nox_runpod/stage0/nox_parallel_provenance_auditor.py' "$R/tools/nox_parallel_provenance_auditor.py"
start_supervisor "PROVENANCE_CPU" "/usr/bin/python3 -u $R/tools/nox_parallel_provenance_auditor.py $ROLE"
if [ "$ROLE" = A40 ];then
 # Process 3: separate CUDA teacher stream, automatic VRAM guard before starting.
 SECOND_URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/c15e52c939feee847a2079def0d0b1080b748319/nox_runpod/stage0/a40_cuda_secondary_memory.py'
 install_py "$SECOND_URL" "$R/tools/a40_cuda_secondary_memory.py"
 cat >"$S/a40_secondary_guard.sh" <<'GUARD'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits|head -1|tr -d ' ')
temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits|head -1|tr -d ' ')
if [ "$free" -lt 15000 ] || [ "$temp" -ge 75 ];then
 echo "WAIT_GPU_MEMORY_OR_TEMP freeMiB=$free tempC=$temp";exit 0
fi
exec "$R/prime9b-venv/bin/python" -u "$R/tools/a40_cuda_secondary_memory.py"
GUARD
 chmod 700 "$S/a40_secondary_guard.sh"
 start_supervisor "CUDA_SECONDARY" "bash $S/a40_secondary_guard.sh"
 # Process 4: provenance-preserving memory ingestion from all three teachers.
 MEMORY_URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/bf3c5dfacbd5bdb9aae66a69cbb251d126171aed/nox_runpod/stage0/a40_memory_neural_integrator.py'
 install_py "$MEMORY_URL" "$R/tools/a40_memory_neural_integrator.py"
 start_supervisor "S03_MEMORY_CPU" "/usr/bin/python3 -u $R/tools/a40_memory_neural_integrator.py --role memory"
fi
echo "NOX_${ROLE}_2_OR_4_ROLES_DISPATCHED"
echo "CHECK_LOGS=$R/logs"
echo "NO_ADAPTERS_NO_MODEL_WEIGHT_OVERWRITES"
