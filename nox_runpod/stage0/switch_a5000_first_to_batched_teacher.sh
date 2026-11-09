#!/usr/bin/env bash
# Safely upgrade the ONE A5000 CUDA teacher process to adaptive batching.
# Preserves prior JSONL; leaves secondary process, weights, and all checkpoints intact.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_pure_distillation"
T="$R/tools/a5000_pure_distillation.py"
L="$R/logs/NOX_A5000_PURE_DISTILLATION.log"
mkdir -p "$S" "$R/tools" "$R/logs" "$R/distillation"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *"A5000"* ]] || { echo HOLD_WRONG_GPU;exit 11; }
PY="$R/prime9b-venv/bin/python"
test -x "$PY" || { echo HOLD_PYTHON_MISSING;exit 12; }
test -s "$R/models/NOX_PRIME_9B_INHERITED/config.json" || { echo HOLD_TEACHER_MISSING;exit 13; }
exec 9>"$S/batched_upgrade.lock"
flock -n 9 || { echo NOX_A5000_UPGRADE_ALREADY_RUNNING;exit 0; }
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/e3012aa0f2d4849976c3d238342ef179e82db49b/nox_runpod/stage0/a5000_batched_one_model_teacher.py'
curl -fLsS --retry 4 "$URL" -o "$T.new"
"$PY" -m py_compile "$T.new"
# Snapshot the existing script and metadata before replacing executable source.
if [ -s "$T" ];then cp -n "$T" "$S/previous_first_stream.py" || true;fi
if [ -f "$R/distillation/NOX_A5000_PURE_DISTILLATION.jsonl" ];then
  "$PY" - <<'PY'
import pathlib,json
p=pathlib.Path("/workspace/nox/distillation/NOX_A5000_PURE_DISTILLATION.jsonl")
count=0
with p.open(encoding="utf-8") as f:
 for line in f:
  try:
   r=json.loads(line)
   if r.get("id"):count+=1
  except ValueError:pass
print("NOX_EXISTING_EXAMPLES_PRESERVED",count,flush=True)
PY
fi
mv -f "$T.new" "$T"
echo "NOX_BATCHED_FIRST_SOURCE_INSTALLED"
# Signal ONLY matching Python workers; the existing supervisor restarts the new source.
mapfile -t workers < <(ps -eo pid=,args= | awk '$0 ~ /[p]ython.*[a]5000_pure_distillation.py/ {print $1}')
for pid in "${workers[@]}";do
  cmd="$(ps -p "$pid" -o args= || true)"
  if [[ "$cmd" == *"$T"* && "$cmd" == *python* ]];then
    kill -TERM "$pid"
    echo "NOX_FIRST_TEACHER_GRACEFUL_RESTART_SIGNAL pid=$pid"
  fi
done
# If original supervisor is not present, create a single lock-guarded supervisor.
superpid="$S/supervisor.pid"
alive=0
if [ -s "$superpid" ] && kill -0 "$(cat "$superpid")" 2>/dev/null;then
 cmd="$(ps -p "$(cat "$superpid")" -o args= || true)"
 if [[ "$cmd" == *"a5000_pure_distillation/supervise.sh"* ]];then alive=1;fi
fi
if [ "$alive" = 0 ];then
  cat > "$S/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox; S="$R/dispatcher/a5000_pure_distillation"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
  NOX_A5000_MAX_BATCH=4 "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_pure_distillation.py" >>"$R/logs/NOX_A5000_PURE_DISTILLATION.log" 2>&1 || true
  sleep 45
done
SUP
  chmod 700 "$S/supervise.sh"
  nohup setsid bash "$S/supervise.sh" </dev/null >> "$R/logs/NOX_A5000_PURE_SUPERVISOR.log" 2>&1 &
  echo $! > "$superpid"
  echo "NOX_BATCHED_SUPERVISOR_STARTED pid=$(cat "$superpid")"
else
  echo "NOX_EXISTING_SUPERVISOR_RETAINED pid=$(cat "$superpid")"
fi
echo "NOX_A5000_BATCHED_FIRST_STREAM_REQUESTED"
echo "NO_SECOND_9B_MODEL_REQUIRED; NO_ADAPTERS; NO_WEIGHT_CHECKPOINT_OVERWRITES"
echo "LOG=$L"
