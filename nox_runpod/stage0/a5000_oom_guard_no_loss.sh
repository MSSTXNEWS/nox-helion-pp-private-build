#!/usr/bin/env bash
# NOX A5000 OOM triage: freeze redundant second/third CUDA launchers,
# preserve primary teacher and all checkpoints.
set -Eeuo pipefail
R=/workspace/nox; D="$R/dispatcher"; L="$R/logs"
mkdir -p "$D/a5000_oom_guard" "$L"
exec 9>"$D/a5000_oom_guard/repair.lock"
flock -n 9 || { echo NOX_OOM_REPAIR_ALREADY_RUNNING; exit 0; }
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" == *A5000* ]] || { echo HOLD_NOT_A5000; exit 10; }
echo "NOX_579_PLUS_SAVED_EXAMPLES_UNTOUCHED"
echo "NOX_OOM_GPU_BEFORE:"
nvidia-smi --query-compute-apps=pid,used_gpu_memory --format=csv,noheader || true
# Halt repeat launches of known competing teacher workflows, not the primary.
for dir in a5000_cuda_secondary a5000_boost_v2 a5000_two_pure_cuda a5000_cuda_third; do
 if [ -d "$D/$dir" ]; then
  touch "$D/$dir/STOP"
  echo "NOX_AUX_NEW_LAUNCH_BLOCKED $dir"
 fi
done
# Only terminate clearly identified competing teacher generation workers.
# No broad pkill; never target a5000_pure_distillation.py or nox_knowledge_extended.py.
python3 - <<'PY'
import os,pathlib,signal,subprocess
prefixes=("a5000_cuda_secondary_direct.py","a5000_boost_second_cuda.py",
          "a5000_third_cuda.py","a5000_cuda_third.py",
          "a5000_two_pure_cuda.py")
pids=set()
for entry in pathlib.Path("/proc").iterdir():
 if not entry.name.isdecimal():continue
 pid=int(entry.name)
 if pid==os.getpid():continue
 try:
  cmd=(entry/"cmdline").read_bytes().replace(b"\x00",b" ").decode("utf8","replace")
 except (OSError,PermissionError):continue
 if not any(x in cmd for x in prefixes):continue
 if "python" not in cmd:continue
 pids.add((pid,cmd[:220]))
for pid,cmd in sorted(pids):
 print("NOX_AUX_TERMINATION_REQUESTED",pid,cmd,flush=True)
 try:os.kill(pid,signal.SIGTERM)
 except ProcessLookupError:pass
PY
# Never restart an already live primary worker.
echo "NOX_A5000_GPU_AFTER_STOP_REQUEST:"
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.free,temperature.gpu --format=csv
echo "NOX_PRIMARY_PROCESSES:"
ps -eo pid,args | grep -E '[a]5000_pure_distillation.py|[n]ox_knowledge_extended.py' || true
if [ -s "$R/distillation/NOX_A5000_PURE_DISTILLATION.jsonl" ];then
 python3 - <<'PY'
import pathlib,json
p=pathlib.Path("/workspace/nox/distillation/NOX_A5000_PURE_DISTILLATION.jsonl")
count=0
with p.open(encoding="utf-8") as f:
 for line in f:
  try:
   if json.loads(line).get("id"):count+=1
  except ValueError:pass
print("NOX_PRIMARY_EXAMPLES_SAVED",count,flush=True)
PY
fi
echo "NOX_OOM_GUARD_APPLIED; NO_MODELS_DELETED; PRIMARY_SUPERVISOR_UNTOUCHED"
