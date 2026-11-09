#!/usr/bin/env bash
# Emergency NOX A5000 recovery: restore proven single-stream source; preserve all data.
set -Eeuo pipefail
R=/workspace/nox; S="$R/dispatcher/a5000_pure_distillation"
T="$R/tools/a5000_pure_distillation.py"; L="$R/logs/NOX_A5000_PURE_DISTILLATION.log"
PY="$R/prime9b-venv/bin/python"
mkdir -p "$S" "$R/logs" "$R/tools"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A5000* ]] || { echo HOLD_WRONG_GPU;exit 20; }
test -x "$PY" || { echo HOLD_PYTHON_ENV_MISSING;exit 21; }
exec 9>"$S/recovery.lock";flock -n 9 || { echo NOX_RECOVERY_ALREADY_RUNNING;exit 0; }
# Preserve every byte of accumulated output; no modifications to checkpoint or models.
"$PY" - <<'PY'
import pathlib,json
p=pathlib.Path("/workspace/nox/distillation/NOX_A5000_PURE_DISTILLATION.jsonl")
count=0
if p.exists():
 with p.open(encoding="utf-8") as f:
  for line in f:
   try:
    if json.loads(line).get("id"):count+=1
   except ValueError:pass
print("NOX_TRAINING_EXAMPLES_RETAINED",count,flush=True)
PY
# Never stop a live worker. If GPU learner is already alive, report and exit.
mapfile -t workers < <(ps -eo pid=,args= | awk '$0 ~ /[p]ython.*\/workspace\/nox\/tools\/a5000_pure_distillation.py/ {print $1}')
if [ "${#workers[@]}" -gt 0 ];then
 echo "NOX_FIRST_GPU_WORKER_ALREADY_ACTIVE pid=${workers[*]}"
 nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv
 exit 0
fi
# Older known working single-example source, not the recently failing batched implementation.
PREV="$S/previous_first_stream.py"
if [ -s "$PREV" ];then
 "$PY" -m py_compile "$PREV"
 cp "$PREV" "$T.new"
else
 curl -fLsS --retry 3 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/24115fda1a16d7de74ea54e9bf8b8d04bfc8a662/nox_runpod/stage0/a5000_pure_distillation.py' -o "$T.new"
 "$PY" -m py_compile "$T.new"
fi
mv -f "$T.new" "$T"
echo NOX_BATCHED_SCRIPT_ROLLED_BACK
# Existing supervisor remains responsible for restarts when alive. No duplicate.
pidfile="$S/supervisor.pid"
if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null;then
 cmd="$(ps -p "$(cat "$pidfile")" -o args= || true)"
 if [[ "$cmd" == *a5000_pure_distillation/supervise.sh* ]];then
  echo "NOX_EXISTING_SUPERVISOR_ALIVE pid=$(cat "$pidfile")"
 else
  echo "NOX_EXISTING_PID_UNKNOWN_HOLD cmd=$cmd";exit 23
 fi
else
 cat > "$S/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_pure_distillation"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
 "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_pure_distillation.py" >> "$R/logs/NOX_A5000_PURE_DISTILLATION.log" 2>&1 || true
 sleep 20
done
SUP
 chmod 700 "$S/supervise.sh"
 nohup setsid bash "$S/supervise.sh" </dev/null >> "$R/logs/NOX_A5000_PURE_SUPERVISOR.log" 2>&1 &
 echo "$!" > "$pidfile"
 echo "NOX_FIRST_SUPERVISOR_RECOVERED pid=$(cat "$pidfile")"
fi
if [ -e "$S/STOP" ];then
 echo "NOX_FIRST_STREAM_STOP_FILE_PRESENT: leaving HOLD to prevent unintended override"
 exit 24
fi
echo "NOX_FIRST_STREAM_RECOVERY_REQUESTED; latest logs:"
tail -n 12 "$L" || true
echo "NOX_NO_ADAPTERS_NO_WEIGHT_DELETION"
