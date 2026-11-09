#!/usr/bin/env bash
# NOX A5000: stop legacy adapter trainer while preserving all completed passes.
# Switch to real CUDA teacher-data distillation, but DO NOT call that full weight absorption.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_pure_distillation"
LOG="$R/logs"
mkdir -p "$S" "$LOG" "$R/tools"
exec 9>"$S/switch.lock"
flock -n 9 || { echo "NOX_A5000_SWITCH_ALREADY_RUNNING";exit 0; }
test "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" = "NVIDIA RTX A5000" || { echo HOLD_WRONG_GPU;exit 21; }
# Require a saved legacy checkpoint before signalling the long-running trainer.
if [ ! -s "$R/checkpoints/NOX_9B_KNOWLEDGE/pass1/SUCCESS.json" ];then
 echo HOLD_NO_VERIFIED_LEGACY_CHECKPOINT;exit 22
fi
echo "NOX_PREVIOUS_TRAINING_PASSES=$(find "$R/checkpoints/NOX_9B_KNOWLEDGE" -name SUCCESS.json | wc -l)"
# Stop ONLY the targeted legacy Python script; never stop pod, delete weights or touch another process.
mapfile -t pids < <(ps -eo pid=,args= | awk '$0 ~ /[p]ython.*[n]ox_knowledge_extended.py/ {print $1}')
for pid in "${pids[@]}";do
 cmd="$(ps -p "$pid" -o args= || true)"
 if [[ "$cmd" == *"python"* && "$cmd" == *"/workspace/nox/tools/nox_knowledge_extended.py"* ]];then
  kill -TERM "$pid"
  echo "NOX_LEGACY_QLORA_SIGTERM pid=$pid; checkpoint saved passes preserved"
 fi
done
deadline=$((SECONDS+45))
while ((SECONDS<deadline));do
 active="$(ps -eo args= | grep -E '[/]workspace/nox/tools/nox_knowledge_extended.py' | head -1 || true)"
 [ -z "$active" ] && break
 sleep 3
done
if ps -eo args= | grep -qE '[/]workspace/nox/tools/nox_knowledge_extended.py';then
 echo "HOLD_LEGACY_TRAINER_STILL_RUNNING; NO_SECOND_GPU_TRAINER"
 exit 23
fi
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/24115fda1a16d7de74ea54e9bf8b8d04bfc8a662/nox_runpod/stage0/a5000_pure_distillation.py'
PY="$R/prime9b-venv/bin/python"
test -x "$PY" || { echo HOLD_NO_WORKING_VENV;exit 24; }
curl -fLsS --retry 3 "$URL" -o "$R/tools/a5000_pure_distillation.py.new"
"$PY" -m py_compile "$R/tools/a5000_pure_distillation.py.new"
mv -f "$R/tools/a5000_pure_distillation.py.new" "$R/tools/a5000_pure_distillation.py"
if [ -s "$S/supervisor.pid" ] && kill -0 "$(cat "$S/supervisor.pid")" 2>/dev/null;then
 echo "NOX_PURE_MULTIPASS_TEACHER_ALREADY_STARTED";exit 0
fi
cat > "$S/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_pure_distillation"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
 "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_pure_distillation.py" >>"$R/logs/NOX_A5000_PURE_DISTILLATION.log" 2>&1 || true
 sleep 45
done
SUP
chmod 700 "$S/supervise.sh"
nohup setsid bash "$S/supervise.sh" </dev/null >/dev/null 2>&1 &
pid=$!
echo "$pid" > "$S/supervisor.pid"
sleep 2
kill -0 "$pid" 2>/dev/null || { echo NOX_PURE_MULTIPASS_LAUNCH_FAILED;exit 25; }
echo "NOX_A5000_PURE_MULTIPASS_DATA_DISTILLATION_STARTED pid=$pid"
echo "NO_LORA_ADAPTER_CREATED_BY_NEW_JOB; NOT_YET_FULL_WEIGHT_STUDENT_TRAINING"
echo "PREVIOUS_COMPLETED_CHECKPOINTS_UNTOUCHED"
