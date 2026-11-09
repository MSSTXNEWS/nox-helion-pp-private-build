#!/usr/bin/env bash
# NOX A40 watchdog recovery: one mutually exclusive GPU-owner.
# True full-parameter training gets priority when already active; otherwise revive
# the previously proven CUDA teacher generator. All saved datasets/checkpoints preserved.
set -Eeuo pipefail
R=/workspace/nox
W="$R/dispatcher/a40_watchdog"
mkdir -p "$W" "$R/logs"
exec 9>"$W/setup.lock"
flock -n 9 || { echo NOX_A40_WATCHDOG_SETUP_BUSY;exit 0; }
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A40* ]] || { echo HOLD_NOT_A40;exit 11; }
test -x "$R/prime9b-venv/bin/python" || { echo HOLD_CUDA_ENV_MISSING;exit 12; }
# Preserve S03 and all model weights.
test -s "$R/tools/a40_cuda_distillation_direct.py" || { echo HOLD_TEACHER_SOURCE_MISSING;exit 13; }
if [ -s "$W/watchdog.pid" ] && kill -0 "$(cat "$W/watchdog.pid")" 2>/dev/null;then
 cmd="$(ps -p "$(cat "$W/watchdog.pid")" -o args= || true)"
 if [[ "$cmd" == *a40_watchdog* ]];then echo "NOX_A40_WATCHDOG_ALREADY_RUNNING pid=$(cat "$W/watchdog.pid")";exit 0;fi
 echo HOLD_PID_MISMATCH;exit 14
fi
cat > "$W/watch.sh" <<'WATCH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
W="$R/dispatcher/a40_watchdog"
T="$R/dispatcher/a40_full_parameter"
G="$R/dispatcher/a40_direct"
LOG="$R/logs/NOX_A40_WATCHDOG.log"
exec 8>"$W/watch.lock"
flock -n 8 || exit 0
record(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG"; }
while [ ! -e "$W/STOP" ];do
 # Only a real training Python process counts; a stale supervisor PID is not training.
 if ps -eo args= | grep -qE '[/]workspace/nox/tools/a40_full_parameter_distill_cycle.py';then
  record "NOX_FULL_WEIGHT_TRAINING_ACTIVE; KEEP_GPU_TEACHERS_PAUSED"
 else
  st=""
  if [ -s "$T/progress.json" ];then
    st="$(python3 - "$T/progress.json" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1])).get("status","UNKNOWN"))
except Exception: print("INVALID")
PY
)"
  fi
  if [ "$st" = COMPLETE_VERIFIED ];then
   record "FULL_WEIGHT_CYCLE_COMPLETE_VERIFIED; NO_RESTART_UNTIL_BACKUP"
  else
   # Full trainer is not running. Cancel its stale GPU reservation/supervisor
   # only by setting STOP, and resume the previously working teacher generator.
   # No destructive SIGKILL, no model deletion.
   if [ -d "$T" ];then touch "$T/STOP";fi
   rm -f "$G/STOP"
   if ! ps -eo args= | grep -qE '[/]workspace/nox/tools/a40_cuda_distillation_direct.py';then
     if [ -f "$G/supervisor.pid" ] && kill -0 "$(cat "$G/supervisor.pid")" 2>/dev/null;then
       cmd="$(ps -p "$(cat "$G/supervisor.pid")" -o args= || true)"
       if [[ "$cmd" == *a40_direct/supervise.sh* ]];then
         record "EXISTING_TEACHER_SUPERVISOR_ALIVE_WAIT_FOR_RESTART"
       else
         record "TEACHER_SUPERVISOR_PID_STALE";rm -f "$G/supervisor.pid"
       fi
     fi
     if [ ! -s "$G/supervisor.pid" ] || ! kill -0 "$(cat "$G/supervisor.pid")" 2>/dev/null;then
       mkdir -p "$G"
       cat >"$G/watchdog_supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
G="$R/dispatcher/a40_direct"
exec 7>"$G/watchdog_supervise.lock"
flock -n 7 || exit 0
while [ ! -e "$G/STOP" ] && [ ! -e "$R/dispatcher/a40_watchdog/STOP" ];do
  /workspace/nox/prime9b-venv/bin/python -u /workspace/nox/tools/a40_cuda_distillation_direct.py >> /workspace/nox/logs/NOX_A40_CUDA_DISTILLATION.log 2>&1 || true
  sleep 30
done
SUP
       chmod 700 "$G/watchdog_supervise.sh"
       nohup setsid bash "$G/watchdog_supervise.sh" </dev/null >>"$R/logs/NOX_A40_WATCHDOG_SUPERVISOR.log" 2>&1 &
       echo $! > "$G/supervisor.pid"
       record "NOX_TEACHER_CUDA_RECOVERY_REQUESTED pid=$(cat "$G/supervisor.pid") previous_full_status=$st"
     fi
   else
     record "NOX_TEACHER_CUDA_ALREADY_ACTIVE"
   fi
  fi
 fi
 python3 - "$W/status.json" "$st" <<'PY'
import datetime,json,os,pathlib,sys
path=pathlib.Path(sys.argv[1])
doc={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
"watchdog":"RUNNING","full_parameter_cycle_status":sys.argv[2],
"recovery_policy":"teacher generation if no full-parameter optimizer active",
"no_adapters":True,"weights_modified_by_watchdog":False}
tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2));os.replace(tmp,path)
PY
 sleep 30
done
WATCH
chmod 700 "$W/watch.sh"
nohup setsid bash "$W/watch.sh" </dev/null >>"$R/logs/NOX_A40_WATCHDOG_SUPERVISOR.log" 2>&1 &
pid=$!;echo "$pid" > "$W/watchdog.pid"
sleep 3
kill -0 "$pid" 2>/dev/null || { echo HOLD_WATCHDOG_START_FAILED;exit 15; }
echo "NOX_A40_WATCHDOG_STARTED pid=$pid"
echo "NOX_A40_RECOVERY_AUTOMATIC_30_SEC"
echo "NO_LOSS_NO_ADAPTERS_NO_POD_STOP"
