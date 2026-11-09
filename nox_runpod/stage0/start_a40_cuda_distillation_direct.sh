#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_direct"
mkdir -p "$S" "$R/logs" "$R/tools"
test "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | xargs)" = "NVIDIA A40" || { echo HOLD_NOT_A40;exit 10; }
PY="$R/prime9b-venv/bin/python"
test -x "$PY" || { echo HOLD_EXISTING_PYTORCH_VENV_MISSING;exit 11; }
test -s "$R/models/NOX_PRIME_9B_INHERITED/config.json" || { echo HOLD_TEACHER_BASE_MISSING;exit 12; }
test -s "$R/tools/nox_prime_9b.py" || { echo HOLD_PYTORCH_LOADER_MISSING;exit 13; }
exec 9>"$S/start.lock"
flock -n 9 || { echo NOX_A40_START_ALREADY_IN_PROGRESS;exit 0; }
SRC='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/0e5c09ee39d4bcb03c96fa92a476b66a36783471/nox_runpod/stage0/a40_cuda_distillation_direct.py'
curl -fLsS --retry 3 "$SRC" -o "$R/tools/a40_cuda_distillation_direct.py.new"
"$PY" -m py_compile "$R/tools/a40_cuda_distillation_direct.py.new"
mv "$R/tools/a40_cuda_distillation_direct.py.new" "$R/tools/a40_cuda_distillation_direct.py"
if [ -s "$S/supervisor.pid" ] && kill -0 "$(cat "$S/supervisor.pid")" 2>/dev/null;then
 echo "NOX_A40_DISTILLATION_ALREADY_RUNNING pid=$(cat "$S/supervisor.pid")";exit 0
fi
cat > "$S/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_direct"
exec 8>"$S/supervise.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
 "$R/prime9b-venv/bin/python" -u "$R/tools/a40_cuda_distillation_direct.py" >>"$R/logs/NOX_A40_CUDA_DISTILLATION.log" 2>&1 || true
 printf '%s RESTART_AFTER_EXIT\n' "$(date -u +%FT%TZ)" >>"$R/logs/NOX_A40_CUDA_RESTARTS.log"
 sleep 60
done
SUP
chmod 700 "$S/supervise.sh"
nohup setsid bash "$S/supervise.sh" </dev/null >/dev/null 2>&1 &
p=$!
echo "$p" > "$S/supervisor.pid"
sleep 2
kill -0 "$p" 2>/dev/null || { echo NOX_A40_SUPERVISOR_START_FAILED;exit 14; }
echo "NOX_A40_CUDA_DISTILLATION_SUPERVISOR_STARTED pid=$p"
echo "ACTUAL_CUDA_LOADING_AND_EXAMPLES_CHECK_LOG=/workspace/nox/logs/NOX_A40_CUDA_DISTILLATION.log"
echo "A5000_WEIGHTS_AND_CHECKPOINTS_UNTOUCHED"
