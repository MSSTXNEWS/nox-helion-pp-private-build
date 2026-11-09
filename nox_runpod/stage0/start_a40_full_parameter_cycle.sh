#!/usr/bin/env bash
# A40 NOX: prioritize FULL 9B student optimizer training instead of legacy teacher
# generation. Fully safe queue: preflight before stopping any running inference,
# no adapters and no modifications to A5000 processes/checkpoints.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_full_parameter"
MODEL="$R/models/NOX_9B_UNIFIED"
MEMORY="$R/memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
PY="$R/prime9b-venv/bin/python"
mkdir -p "$S" "$R/tools" "$R/logs"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A40* ]] || { echo HOLD_NOT_A40;exit 11; }
test -x "$PY" || { echo HOLD_NO_PYTORCH_ENV;exit 12; }
test -s "$MODEL/NOX_UNIFIED_RECEIPT.json" || { echo HOLD_NO_VERIFIED_NOX_9B_BASE;exit 13; }
test -s "$MEMORY" || { echo HOLD_S03_MEMORY_NOT_READY;exit 14; }
exec 9>"$S/launch.lock"
flock -n 9 || { echo NOX_A40_TRAINING_SETUP_ALREADY_RUNNING;exit 0; }
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/2e59063d13d186a796b416efdac9abff77b6cedd/nox_runpod/stage0/a40_full_parameter_distill_cycle.py'
curl -fLsS --retry 4 "$URL" -o "$R/tools/a40_full_parameter_distill_cycle.py.new"
"$PY" -m py_compile "$R/tools/a40_full_parameter_distill_cycle.py.new"
mv -f "$R/tools/a40_full_parameter_distill_cycle.py.new" "$R/tools/a40_full_parameter_distill_cycle.py"
# Real resource/data preflight before stopping teacher inference. If full trainer
# fails this preflight, its script generates HOLD and no model is interrupted.
# The full trainer will independently re-check before allocating any weights.
"$PY" - <<'PY'
from pathlib import Path
import sqlite3,sys,shutil
r=Path('/workspace/nox')
db=r/'memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3'
c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
try:
 n=c.execute("select count(*) from knowledge where teacher != 'UNATTRIBUTED'").fetchone()[0]
except sqlite3.Error:
 print("HOLD_S03_SCHEMA_UNAVAILABLE",flush=True);sys.exit(20)
finally:c.close()
print("NOX_FULL_TRAIN_DATASET_EXAMPLES",n,flush=True)
if n<48:print("HOLD_S03_NEEDS_48_EXAMPLES",flush=True);sys.exit(21)
free=shutil.disk_usage('/opt').free//1024**3
print("NOX_A40_EPHEMERAL_SPACE_GIB",free,flush=True)
if free<23:print("HOLD_EPHEMERAL_DISK_LT_23_GIB",flush=True);sys.exit(22)
PY
if [ -s "$S/supervisor.pid" ] && kill -0 "$(cat "$S/supervisor.pid")" 2>/dev/null;then
 echo "NOX_A40_FULL_PARAMETER_SUPERVISOR_ALREADY_RUNNING pid=$(cat "$S/supervisor.pid")";exit 0
fi
# Requested switch from teacher synthesis to actual all-parameter student training.
# STOP signals are honored after each current generation item; no SIGKILL/pod stop.
for d in a40_direct a40_secondary a40_accelerator a40 a40_v4;do
 if [ -d "$R/dispatcher/$d" ];then touch "$R/dispatcher/$d/STOP";fi
done
echo "NOX_A40_CUDA_TEACHER_STREAMS_STOP_REQUESTED_AFTER_CURRENT_ITEM"
# Keep independent A40 S03 memory ingestion running, and leave A5000 alone.
cat > "$S/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_full_parameter"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
  free="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')"
  temp="$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1 | tr -d ' ')"
  if [ "$free" -ge 37888 ] && [ "$temp" -lt 75 ];then
    "$R/prime9b-venv/bin/python" -u "$R/tools/a40_full_parameter_distill_cycle.py" --steps 20 \
      >>"$R/logs/NOX_A40_FULL_PARAMETER_TRAINING.log" 2>&1 || true
    # Never blindly loop training after completion or an out-of-memory HOLD.
    echo "$(date -u +%FT%TZ) FULL_PARAMETER_CYCLE_EXITED_NO_AUTO_REPEAT" >>"$R/logs/NOX_A40_FULL_PARAMETER_TRAINING.log"
    exit 0
  fi
  /usr/bin/python3 - "$S/progress.json" "$free" "$temp" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1])
data={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
"status":"WAIT_GPU","stage":"A40_TEACHER_SHUTDOWN_AND_MEMORY_RELEASE",
"cycle_progress_percent":0,"steps_executed_this_cycle":0,
"target_steps_this_cycle":20,"free_gpu_mib":int(sys.argv[2]),
"gpu_temp_c":int(sys.argv[3]),"adapters_allowed":False,
"all_teacher_knowledge_absorbed_percent":None}
tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));os.replace(tmp,p)
PY
  sleep 20
done
SUP
chmod 700 "$S/supervise.sh"
nohup setsid bash "$S/supervise.sh" </dev/null >>"$R/logs/NOX_A40_FULL_PARAMETER_SUPERVISOR.log" 2>&1 &
p=$!;echo "$p" > "$S/supervisor.pid"
sleep 2
kill -0 "$p" 2>/dev/null || { echo HOLD_TRAINING_SUPERVISOR_FAILED;exit 25; }
echo "NOX_A40_FULL_PARAMETER_CYCLE_QUEUED pid=$p"
echo "PROGRESS_0_TO_100=$S/progress.json"
echo "TRAINING_LOG=$R/logs/NOX_A40_FULL_PARAMETER_TRAINING.log"
echo "A5000_UNTOUCHED; NO_ADAPTERS; FINAL_WEIGHTS_STAGED_ON_EPHEMERAL_DISK"
