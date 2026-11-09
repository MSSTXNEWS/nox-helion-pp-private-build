#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
D="$R/dispatcher/a5000_boost_v2"
L="$R/logs"
mkdir -p "$D" "$L" "$R/tools"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A5000* ]] || { echo HOLD_WRONG_GPU;exit 20; }
PY="$R/prime9b-venv/bin/python"
test -x "$PY" && test -s "$R/models/NOX_PRIME_9B_INHERITED/config.json" || { echo HOLD_MODEL_OR_PYTHON_MISSING;exit 21; }
# Never interrupt the existing teacher or any ongoing full-weight training.
if ps -eo args= | grep -Eq '[p]ython.*[/]workspace/nox/tools/a5000_second_cuda_distillation.py'; then echo NOX_A5000_SECOND_TEACHER_ALREADY_COMPUTING; nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv;exit 0;fi
# Supersede only the older *second-lane* supervisor. It never owns the first lane.
OLD="$R/dispatcher/a5000_two_cuda"
if [ -d "$OLD" ];then touch "$OLD/STOP";fi
U='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/53acfb4d9c5c110dabdfc6e45182ee2068d49dea/nox_runpod/stage0/a5000_second_cuda_distillation.py'
curl -fLsS --retry 3 "$U" -o "$R/tools/a5000_second_cuda_distillation.py.new"
"$PY" -m py_compile "$R/tools/a5000_second_cuda_distillation.py.new"
mv -f "$R/tools/a5000_second_cuda_distillation.py.new" "$R/tools/a5000_second_cuda_distillation.py"
cat > "$D/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
D="$R/dispatcher/a5000_boost_v2"
exec 9>"$D/supervisor.lock"
flock -n 9 || exit 0
while [ ! -e "$D/STOP" ];do
 free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -dc '0-9')
 temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1 | tr -dc '0-9')
 # 2x ~8GB Qwen3.5-9B 4-bit model loads require headroom. Never force OOM.
 if [ -n "$free" ] && [ "$free" -ge 10500 ] && [ "$temp" -lt 73 ];then
  echo "$(date -u +%FT%TZ) NOX_SECOND_GPU_DISTILLATION_START free=$free" >>"$R/logs/NOX_A5000_BOOST_V2.log"
  "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_second_cuda_distillation.py" >>"$R/logs/NOX_A5000_BOOST_V2.log" 2>&1 || true
 else
  echo "$(date -u +%FT%TZ) NOX_SECOND_GPU_HOLD free=$free temp=$temp" >>"$R/logs/NOX_A5000_BOOST_V2.log"
 fi
 sleep 30
done
SUP
chmod 700 "$D/supervise.sh"
exec 8>"$D/launch.lock";flock -n 8 || { echo NOX_BOOST_ALREADY_LAUNCHING;exit 0; }
if [ -s "$D/supervisor.pid" ] && kill -0 "$(cat "$D/supervisor.pid")" 2>/dev/null;then
 echo "NOX_A5000_BOOST_ALREADY_RUNNING pid=$(cat "$D/supervisor.pid")"
else
 nohup setsid bash "$D/supervise.sh" </dev/null >>"$L/NOX_A5000_BOOST_V2.log" 2>&1 &
 echo $! > "$D/supervisor.pid"
 echo "NOX_A5000_BOOST_SUPERVISOR_STARTED pid=$(cat "$D/supervisor.pid")"
fi
echo "FIRST_TEACHER_UNTOUCHED; NO_ADAPTERS; CHECK=$L/NOX_A5000_BOOST_V2.log"
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv
