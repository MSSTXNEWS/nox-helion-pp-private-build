#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_memory_only"
mkdir -p "$S" "$R/tools" "$R/logs" "$R/memory"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A40* ]] || { echo HOLD_WRONG_NODE;exit 11; }
exec 9>"$S/setup.lock";flock -n 9 || { echo NOX_MEMORY_SETUP_IN_PROGRESS;exit 0; }
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/f885e7dac4649136d3b503fe0d55a5da618f95b8/nox_runpod/stage0/a40_unified_nox_s03_memory.py'
curl -fsSL --retry 3 "$URL" -o "$R/tools/a40_unified_nox_s03_memory.py.new"
python3 -m py_compile "$R/tools/a40_unified_nox_s03_memory.py.new"
mv "$R/tools/a40_unified_nox_s03_memory.py.new" "$R/tools/a40_unified_nox_s03_memory.py"
pidf="$S/supervisor.pid"
if [ -s "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null;then
 cmd="$(ps -p "$(cat "$pidf")" -o args= || true)"
 if [[ "$cmd" == *a40_memory_only* ]];then
  echo "NOX_S03_MEMORY_ALREADY_RUNNING pid=$(cat "$pidf")";exit 0
 fi
 echo "HOLD_UNEXPECTED_PID_OWNER";exit 12
fi
cat > "$S/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox;S="$R/dispatcher/a40_memory_only"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
 nice -n 10 python3 -u "$R/tools/a40_unified_nox_s03_memory.py" >>"$R/logs/NOX_A40_UNIFIED_S03_MEMORY.log" 2>&1 || true
 sleep 45
done
SUP
chmod 700 "$S/supervise.sh"
nohup setsid bash "$S/supervise.sh" </dev/null >>"$R/logs/NOX_A40_UNIFIED_MEMORY_SUPERVISOR.log" 2>&1 &
p=$!;echo "$p" >"$pidf"
sleep 3
kill -0 "$p" 2>/dev/null || { echo NOX_MEMORY_LAUNCH_FAILED;exit 13; }
echo "NOX_A40_UNIFIED_MEMORY_REQUESTED pid=$p"
echo "SOURCE_SHARED=/workspace/nox"
echo "MEMORY=/workspace/nox/memory/NOX_UNIFIED_S03"
echo "NO_GPU_MODEL_LAUNCHED; CUDA_TRAINING_UNTOUCHED"
