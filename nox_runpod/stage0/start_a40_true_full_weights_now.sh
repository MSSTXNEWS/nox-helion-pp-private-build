#!/usr/bin/env bash
# NOX A40: begin an adapter-free FULL-WEIGHT teacher-to-student cycle.
# Resource gate before stopping any current CUDA teacher. One checkpoint per cycle.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_full_parameter"
V="$R/dispatcher/a40_full_parameter_v2"
W="$R/dispatcher/a40_watchdog"
G="$R/dispatcher/a40_direct"
PY="$R/prime9b-venv/bin/python"
mkdir -p "$S" "$V" "$R/logs" "$R/tools"
exec 9>"$V/launch.lock"
flock -n 9 || { echo NOX_A40_ALL_WEIGHT_LAUNCH_ALREADY_RUNNING; exit 0; }
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader|head -1)" == *A40* ]] || { echo HOLD_NOT_A40;exit 10; }
test -x "$PY" || { echo HOLD_PYTORCH_VENV_MISSING;exit 11; }
test -s "$R/models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json" || { echo HOLD_FULL_NOX_BASE_MISSING;exit 12; }
test -s "$R/memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3" || { echo HOLD_S03_NOT_READY;exit 13; }
# Never duplicate existing full-weight training.
if ps -eo args= | grep -q '[p]ython.*[/]workspace/nox/tools/a40_full_parameter_distill_cycle.py';then
 echo NOX_FULL_WEIGHT_OPTIMIZER_ALREADY_RUNNING
 exit 0
fi
if [ -s "$V/supervisor.pid" ] && kill -0 "$(cat "$V/supervisor.pid")" 2>/dev/null;then
 cmd="$(ps -p "$(cat "$V/supervisor.pid")" -o args= || true)"
 if [[ "$cmd" == *a40_full_parameter_v2* ]];then
  echo "NOX_FULL_WEIGHT_SUPERVISOR_ALREADY_RUNNING pid=$(cat "$V/supervisor.pid")"
  exit 0
 fi
 echo HOLD_UNEXPECTED_PID_OWNER
 exit 14
fi
# The trainer consumes source-labelled 9B teacher data already in S03.
# 27B and DeepSeek32 have no proven samples yet, so this is STAGE 1, not 3/3.
"$PY" - <<'PY'
import datetime,json,os,pathlib,shutil,sqlite3,sys
import torch
r=pathlib.Path("/workspace/nox")
s=r/"dispatcher/a40_full_parameter"
def hold(why,**extra):
 d={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "status":"HOLD","stage":"NOX_9B_ALL_PARAMETER_PREFLIGHT",
  "reason":why,"cycle_progress_percent":0,"steps_executed_this_cycle":0,
  "target_steps_this_cycle":20,"adapters_allowed":False,
  "all_teacher_knowledge_absorbed_percent":None,"details":extra}
 t=s/"progress.json.tmp";t.write_text(json.dumps(d,indent=2));os.replace(t,s/"progress.json")
 print("NOX_A40_FULL_WEIGHTS_HOLD",why,extra,flush=True)
 sys.exit(20)
if not torch.cuda.is_available() or "A40" not in torch.cuda.get_device_name(0):hold("CUDA_A40_NOT_AVAILABLE")
if not hasattr(torch.optim,"Adafactor"):hold("NO_FACTORED_FULL_PARAMETER_OPTIMIZER")
db=r/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
try:
 c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True)
 rows=c.execute("SELECT content,teacher,content_sha FROM knowledge WHERE teacher != 'UNATTRIBUTED'").fetchall()
 c.close()
except Exception as e:hold("S03_DB_UNREADABLE",message=str(e)[:160])
from hashlib import sha256
train=test=0
by_teacher={}
for content,teacher,h in rows:
 if not isinstance(content,str) or not (100<=len(content)<=4000):continue
 if sha256(content.encode()).hexdigest()!=h:continue
 by_teacher[teacher]=by_teacher.get(teacher,0)+1
 if int(h[:8],16)%10==0:test+=1
 else:train+=1
print("NOX_S03_TRAIN_HOLDOUT",train,test,"REAL_TEACHER_COUNTS",by_teacher,flush=True)
if train<32 or test<4:hold("INSUFFICIENT_DISTILLATION_DATA",train=train,holdout=test)
available=0
for l in pathlib.Path("/proc/meminfo").read_text().splitlines():
 if l.startswith("MemAvailable:"):available=int(l.split()[1])//1048576
disk=shutil.disk_usage("/opt").free//1024**3
print("NOX_A40_FREE_CPU_RAM_GIB",available,"FREE_CONTAINER_DISK_GIB",disk,flush=True)
if available<24:hold("INSUFFICIENT_CPU_RAM",free_gib=available,need_gib=24)
if disk<23:hold("INSUFFICIENT_CONTAINER_DISK",free_gib=disk,need_gib=23)
print("NOX_ALL_PARAMETER_PREFLIGHT_PASSED",flush=True)
PY
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/5146b768479a140991e4bf7e09bd1398fd585341/nox_runpod/stage0/a40_full_parameter_distill_cycle.py'
curl -fsSL --retry 3 "$URL" -o "$R/tools/a40_full_parameter_distill_cycle.py.new"
"$PY" -m py_compile "$R/tools/a40_full_parameter_distill_cycle.py.new"
mv -f "$R/tools/a40_full_parameter_distill_cycle.py.new" "$R/tools/a40_full_parameter_distill_cycle.py"
# Stop teacher CUDA generation AFTER data+RAM+disk requirements pass.
# No SIGKILL / no Pod restart / never touch A5000's learning state.
touch "$W/STOP"
for d in a40_direct a40_secondary a40_accelerator a40 a40_v4;do
 if [ -d "$R/dispatcher/$d" ];then touch "$R/dispatcher/$d/STOP";fi
done
rm -f "$V/STOP"
echo NOX_A40_TEACHER_GPU_RELEASE_REQUESTED
cat >"$V/supervise.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
V="$R/dispatcher/a40_full_parameter_v2"
S="$R/dispatcher/a40_full_parameter"
exec 8>"$V/supervisor.lock"
flock -n 8 || exit 0
log="$R/logs/NOX_A40_FULL_PARAMETER_TRAINING.log"
for i in $(seq 1 100);do
 if [ -e "$V/STOP" ];then exit 0;fi
 # GPU must have sufficient memory for BF16 parameters + gradients.
 free="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits|head -1|tr -d ' ')"
 temp="$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits|head -1|tr -d ' ')"
 if [ "$free" -ge 37888 ] && [ "$temp" -lt 75 ];then
  cycle="$(date -u +%Y%m%dT%H%M%SZ)_$$"
  echo "$(date -u +%FT%TZ) BEGIN_TRUE_FULL_PARAMETER_OPTIMIZER cycle=$cycle freeMiB=$free" >> "$log"
  set +e
  "$R/prime9b-venv/bin/python" -u "$R/tools/a40_full_parameter_distill_cycle.py" --steps 20 --cycle "$cycle" >>"$log" 2>&1
  rc=$?
  set -e
  echo "$(date -u +%FT%TZ) FULL_PARAMETER_TRAINER_EXIT=$rc cycle=$cycle" >>"$log"
  break
 fi
 python3 - "$S/progress.json" "$free" "$temp" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1])
x={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
   "status":"WAIT_GPU","stage":"RELEASE_GPU_FOR_ALL_PARAMETER_NOX",
   "cycle_progress_percent":0,"steps_executed_this_cycle":0,
   "target_steps_this_cycle":20,"free_gpu_mib":int(sys.argv[2]),
   "temperature_c":int(sys.argv[3]),"adapters_allowed":False,
   "all_teacher_knowledge_absorbed_percent":None}
t=p.with_suffix(".tmp");t.write_text(json.dumps(x));os.replace(t,p)
PY
 sleep 20
done
python3 - "$S/progress.json" <<'PY'
import json,sys
try:
 x=json.load(open(sys.argv[1]));print("NOX_FULL_TRAINER_FINAL_STATUS",x.get("status"),x.get("reason"))
except Exception as e:print("NOX_PROGRESS_RECEIPT_UNAVAILABLE",str(e))
PY
# Always resume useful verified teacher work after the one bounded optimization
# cycle, even in HOLD. A verified full checkpoint remains untouched on /opt.
rm -f "$R/dispatcher/a40_watchdog/STOP" "$R/dispatcher/a40_direct/STOP"
RECOVERY='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/00c24631297e115efb88b73d95d04848cf9670d7/nox_runpod/stage0/a40_watchdog_recover_if_full_training_on_hold.sh'
curl -fsSL "$RECOVERY" | bash >> "$log" 2>&1 || true
echo "$(date -u +%FT%TZ) FULL_WEIGHT_CYCLE_FINISHED_TEACHER_RECOVERY_REQUESTED" >> "$log"
SUP
chmod 700 "$V/supervise.sh"
nohup setsid bash "$V/supervise.sh" </dev/null >>"$R/logs/NOX_A40_FULL_PARAMETER_SUPERVISOR.log" 2>&1 &
pid=$!
echo "$pid" >"$V/supervisor.pid"
sleep 2
kill -0 "$pid" 2>/dev/null || { echo HOLD_A40_FULL_WEIGHT_SUPERVISOR_FAILED;exit 15; }
echo "NOX_A40_FULL_PARAMETER_20_STEPS_QUEUED pid=$pid"
echo "NOX_PROGRESS=/workspace/nox/dispatcher/a40_full_parameter/progress.json"
echo "NOX_FULL_CHECKPOINT=/opt/nox_full_parameter_A40"
echo "NOX_9B_DATA_FIRST; 27B_AND_DEEPSEEK_PENDING; NO_ADAPTERS; A5000_UNTOUCHED"
