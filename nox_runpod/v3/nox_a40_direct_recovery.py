#!/usr/bin/env python3
"""NOX primary A40 direct full-weight recovery with honest GPU verification.

Run once. Never kill trainers or GPU owners. No adapter, no dummy workload.
Runs only one student cycle if A40 is unowned and current S03 is available.
"""
import datetime,fcntl,json,os,pathlib,subprocess,sys,time
R=pathlib.Path("/workspace/nox")
B=R/"dispatcher/nox_v3/bin"
S=R/"dispatcher/a40_full_parameter"
S.mkdir(parents=True,exist_ok=True)
def gpuowners():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=10)
 if p.returncode!=0:return None
 return [int(v) for v in p.stdout.splitlines() if v.strip().isdigit()]
def emit(status,**info):
 obj={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"status":status,**info}
 print(json.dumps(obj,ensure_ascii=False),flush=True)
def main():
 with (S/"direct_cycle.launch.lock").open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:emit("HOLD_LAUNCH_ALREADY_RUNNING");return 2
  if any((R/"dispatcher/nox_v3"/x).exists() for x in ("STOP_A40","MANUAL_STOP_A40","HOLD_A40")):
   emit("HOLD_MANUAL_SAFETY_MARKER");return 2
  owners=gpuowners()
  if owners is None:emit("HOLD_GPU_QUERY_FAILED");return 2
  if owners:emit("HOLD_GPU_OWNER",pids=owners);return 2
  py=R/"prime9b-venv/bin/python"
  trainer=B/"a40_full_parameter_distill_cycle.py"
  if not py.is_file() or not trainer.is_file():
   emit("HOLD_TRAINER_MISSING",python=str(py),trainer=str(trainer));return 2
  cycle="v3_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
  log=R/"logs/NOX_DIRECT_FULL_PARAMETER_A40.log"
  log.parent.mkdir(parents=True,exist_ok=True)
  with log.open("ab") as out:
   proc=subprocess.Popen([str(py),"-u",str(trainer),"--cycle",cycle,"--steps","20"],
     cwd=str(R),stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
  emit("TRAINER_PROCESS_LAUNCHED_NOT_YET_VERIFIED",pid=proc.pid,cycle=cycle)
  time.sleep(12)
  result={}
  try:result=json.loads((S/"progress.json").read_text(encoding="utf-8"))
  except (OSError,ValueError):pass
  current=gpuowners()
  emit("GPU_TRAINER_ACTIVE" if current and proc.poll() is None else "HOLD_NO_VERIFIED_GPU_PROGRESS",
       cycle=cycle,pid=proc.pid,alive=proc.poll() is None,gpu_owners=current,
       trainer_status=result.get("status"),stage=result.get("stage"),
       steps=result.get("steps_executed_this_cycle"),reason=result.get("reason"))
  return 0 if current and proc.poll() is None else 2
if __name__=="__main__":sys.exit(main())
