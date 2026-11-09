#!/usr/bin/env bash
# A5000 second independent CUDA teacher data worker. No adapters, no weight changes.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_cuda_secondary"
LOG="$R/logs"
mkdir -p "$S" "$LOG" "$R/tools"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader|head -1)" == *A5000* ]] || { echo HOLD_WRONG_GPU;exit 11; }
PY="$R/prime9b-venv/bin/python"
test -x "$PY" || { echo HOLD_PYTHON_ENV;exit 12; }
test -s "$R/models/NOX_PRIME_9B_INHERITED/config.json" || { echo HOLD_NO_9B_TEACHER;exit 13; }
test -s "$R/tools/nox_prime_9b.py" || { echo HOLD_NO_MODEL_LOADER;exit 14; }
exec 9>"$S/start.lock"
flock -n 9 || { echo NOX_SECONDARY_START_ALREADY_RUNNING;exit 0; }
if [ -s "$S/supervisor.pid" ] && kill -0 "$(cat "$S/supervisor.pid")" 2>/dev/null; then
 cmd="$(ps -p "$(cat "$S/supervisor.pid")" -o args= || true)"
 if [[ "$cmd" == *a5000_cuda_secondary* ]]; then
  echo "NOX_A5000_SECONDARY_ALREADY_RUNNING pid=$(cat "$S/supervisor.pid")";exit 0
 fi
 echo "HOLD_PID_OWNERSHIP_UNCERTAIN";exit 15
fi
curl -fsSL --retry 4 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/b4bfedad4725927be960e94c62f4cb41fb2b979d/nox_runpod/stage0/a5000_cuda_secondary_direct.py' -o "$R/tools/a5000_cuda_secondary_direct.py.new"
"$PY" -m py_compile "$R/tools/a5000_cuda_secondary_direct.py.new"
mv -f "$R/tools/a5000_cuda_secondary_direct.py.new" "$R/tools/a5000_cuda_secondary_direct.py"
cat > "$S/supervisor.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_cuda_secondary"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
  read -r free temp < <(nvidia-smi --query-gpu=memory.free,temperature.gpu --format=csv,noheader,nounits | head -1 | tr -d ',')
  if [ "$free" -ge 13000 ] && [ "$temp" -lt 75 ];then
    "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_cuda_secondary_direct.py" >>"$R/logs/NOX_A5000_SECONDARY_DISTILLATION.log" 2>&1 || true
  else
    echo "$(date -u +%FT%TZ) HOLD GPU_FREE_MiB=$free TEMPERATURE_C=$temp" >>"$R/logs/NOX_A5000_SECONDARY_DISTILLATION.log"
  fi
  sleep 60
done
SUP
chmod 700 "$S/supervisor.sh"
nohup setsid bash "$S/supervisor.sh" </dev/null >>"$LOG/NOX_A5000_SECONDARY_SUPERVISOR.log" 2>&1 &
pid=$!
echo "$pid" >"$S/supervisor.pid"
sleep 2
kill -0 "$pid" 2>/dev/null || { echo NOX_SECONDARY_LAUNCH_FAILED;exit 16; }
echo "NOX_A5000_SECONDARY_SUPERVISOR_STARTED pid=$pid"
echo "PRIMARY_TRAINER_UNTOUCHED"
echo "NO_ADAPTERS_CREATED; TEACHER_EXAMPLES_NOT_FULL_WEIGHT_TRAINING"
