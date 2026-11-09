#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox;D="$R/dispatcher/a5000_two_cuda";L="$R/logs"
mkdir -p "$D" "$R/tools" "$L"
test -x "$R/prime9b-venv/bin/python" || { echo HOLD_NO_CUDA_VENV;exit 12; }
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A5000* ]] || { echo HOLD_NOT_A5000;exit 13; }
exec 9>"$D/launch.lock";flock -n 9 || { echo A5000_DUAL_LAUNCH_IN_PROGRESS;exit 0; }
# Active legacy LoRA training is incompatible with user's no-adapters policy;
# never silently kill an active checkpoint writer.
if ps -eo args= | grep -Eq '[p]ython.*[/]workspace/nox/tools/nox_knowledge_extended.py';then
 echo "HOLD_LEGACY_ADAPTER_TRAINER_ACTIVE_SWITCH_REQUIRED; no new CUDA copy started"
 exit 14
fi
# Reuse first validated CUDA teacher, start a second different-purpose dataset lane.
if ! ps -eo args= | grep -Eq '[p]ython.*[/]workspace/nox/tools/a5000_pure_distillation.py';then
 U='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/24115fda1a16d7de74ea54e9bf8b8d04bfc8a662/nox_runpod/stage0/a5000_pure_distillation.py'
 curl -fLsS --retry 3 "$U" -o "$R/tools/a5000_pure_distillation.py.new"
 "$R/prime9b-venv/bin/python" -m py_compile "$R/tools/a5000_pure_distillation.py.new"
 mv -f "$R/tools/a5000_pure_distillation.py.new" "$R/tools/a5000_pure_distillation.py"
 if ! ps -eo args= | grep -Eq '[b]ash.*[/]workspace/nox/dispatcher/a5000_pure_distillation/supervise.sh';then
   mkdir -p "$R/dispatcher/a5000_pure_distillation"
   cat > "$R/dispatcher/a5000_pure_distillation/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
D="$R/dispatcher/a5000_pure_distillation"
exec 9>"$D/supervisor_lock";flock -n 9 || exit 0
while [ ! -e "$D/STOP" ];do
 "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_pure_distillation.py" >>"$R/logs/NOX_A5000_PURE_DISTILLATION.log" 2>&1 || true
 sleep 60
done
SUP
   nohup setsid bash "$R/dispatcher/a5000_pure_distillation/supervise.sh" </dev/null >>"$L/A5000_FIRST_SUPERVISOR.log" 2>&1 &
   echo "A5000_FIRST_CUDA_TEACHER_LAUNCH_REQUESTED pid=$!"
 fi
else
 echo A5000_FIRST_CUDA_ALREADY_RUNNING
fi
U='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/53acfb4d9c5c110dabdfc6e45182ee2068d49dea/nox_runpod/stage0/a5000_second_cuda_distillation.py'
curl -fLsS --retry 3 "$U" -o "$R/tools/a5000_second_cuda_distillation.py.new"
"$R/prime9b-venv/bin/python" -m py_compile "$R/tools/a5000_second_cuda_distillation.py.new"
mv -f "$R/tools/a5000_second_cuda_distillation.py.new" "$R/tools/a5000_second_cuda_distillation.py"
cat > "$D/second_supervisor.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox;D="$R/dispatcher/a5000_two_cuda"
exec 9>"$D/second_supervisor.lock";flock -n 9 || exit 0
while [ ! -e "$D/STOP" ];do
 free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -dc '0-9')
 temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1 | tr -dc '0-9')
 if [ "$free" -ge 10000 ] && [ "$temp" -lt 75 ];then
  "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_second_cuda_distillation.py" >>"$R/logs/NOX_A5000_SECOND_CUDA.log" 2>&1 || true
 else
  echo "$(date -u +%FT%TZ) HOLD_VRAM_OR_TEMP free=$free temp=$temp" >>"$R/logs/NOX_A5000_SECOND_CUDA.log"
 fi
 sleep 60
done
SUP
chmod 700 "$D/second_supervisor.sh"
if [ -s "$D/second.pid" ] && kill -0 "$(cat "$D/second.pid")" 2>/dev/null;then
 echo "A5000_SECOND_CUDA_SUPERVISOR_ALREADY_RUNNING pid=$(cat "$D/second.pid")"
else
 nohup setsid bash "$D/second_supervisor.sh" </dev/null >>"$L/A5000_SECOND_SUPERVISOR.log" 2>&1 &
 echo $! > "$D/second.pid"
 echo "A5000_SECOND_CUDA_SUPERVISOR_STARTED pid=$(cat "$D/second.pid")"
fi
echo "A5000_TWO_ADAPTER_FREE_CUDA_STREAMS_REQUESTED"
