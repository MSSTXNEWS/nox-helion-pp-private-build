#!/usr/bin/env python3
"""NOX V3 10-second watchdog per GPU Pod.

Restarts ONLY our own V3 dispatcher when no process exists, using the existing
safe per-node cutover and supervisor. Does not stop/reboot Pods, kill GPU work,
clear STOP/HOLD, wipe disk or spawn a second trainer. Every 180s evaluates
improvement. Results are persisted per-node to a verified status file.
"""
import argparse,datetime,fcntl,json,os,pathlib,subprocess,sys,time,traceback
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/nox_v3"
BIN=S/"bin"
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+".new")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def run(cmd,timeout):
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,check=False)
  return {"exit":p.returncode,"output":(p.stdout+p.stderr)[-1500:]}
 except (OSError,subprocess.TimeoutExpired) as e:return {"exit":124,"output":repr(e)[:300]}
def ps_running(node):
 script=str(BIN/"nox_v3_dispatcher.py")
 found=[]
 for proc in pathlib.Path("/proc").iterdir():
  if not proc.name.isdigit():continue
  try:
   args=[x.decode(errors="replace") for x in (proc/"cmdline").read_bytes().split(b"\0") if x]
   if script in args and "--node" in args:
    ix=args.index("--node")
    if len(args)>ix+1 and args[ix+1]==node:found.append(int(proc.name))
  except OSError:pass
 return found
def tick(node,improve):
 status={"utc":utc(),"node":node,"watchdog_interval_seconds":60,
         "actions":[],"auto_reboot_pod":False,"auto_kill_training":False}
 if (S/("STOP_"+node)).exists() or (S/("MANUAL_STOP_"+node)).exists() or (S/("HOLD_"+node)).exists():
  status["state"]="HOLD_STOP_MARKER"
 else:
  current=ps_running(node)
  if len(current)>1:
   status["state"]="HOLD_DUPLICATE_DISPATCHERS";status["pids"]=current
  elif len(current)==1:
   status["state"]="DISPATCHER_ALIVE";status["pids"]=current
   # A process existing is not proof of activity. Reload only an explicitly
   # idle, stale dispatcher, after proving no GPU owner and no child process.
   gate_file=S/("cutover_"+node+".json")
   try:gate=json.loads(gate_file.read_text(encoding="utf-8"))
   except (OSError,ValueError):gate={}
   path=S/("orchestrator_status_"+node+".json")
   if not path.is_file():path=S/"orchestrator_status.json"
   try:
    info=json.loads(path.read_text(encoding="utf-8"))
    age=time.time()-path.stat().st_mtime
   except (OSError,ValueError):info={};age=0
   train_path=R/"dispatcher/a40_full_parameter/progress.json"
   try:train_state=json.loads(train_path.read_text(encoding="utf-8"))
   except (OSError,ValueError):train_state={}
   proven_train_error=(node=="A40" and info.get("status")=="HOLD"
      and train_state.get("status")=="ERROR" and train_state.get("stage")=="FULL_PARAMETER_CYCLE_FAILED")
   stale=(info.get("node")==node and
       (info.get("status") in ("PREPARED_NOT_STARTED","HOLD_CUTOVER_SAVEPOINT_PENDING",
                              "HOLD_OLD_OR_FULL_GPU_OWNER_ACTIVE") or proven_train_error)
       and age>20)
   approved=gate.get("node")==node and gate.get("status")=="CUTOVER_READY"
   if stale and approved:
    try:
     gpu=subprocess.run(["nvidia-smi","--query-compute-apps=pid",
       "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
     owners=[x for x in gpu.stdout.splitlines() if x.strip().isdigit()] if gpu.returncode==0 else ["UNAVAILABLE"]
     children=[]
     for p in pathlib.Path("/proc").iterdir():
      if not p.name.isdigit():continue
      try:
       stat=(p/"stat").read_text()
       parent=int(stat.rsplit(")",1)[1].strip().split()[1])
       if parent==current[0]:children.append(int(p.name))
      except (OSError,ValueError,IndexError):pass
     if not owners and not children:
      # One stale idle process. SIGTERM only; never force a live trainer.
      os.kill(current[0],15)
      time.sleep(1)
      if ps_running(node):
       status["state"]="HOLD_IDLE_DISPATCHER_DID_NOT_EXIT"
      else:
       status["state"]="IDLE_DISPATCHER_RELOADED"
       supervisor=BIN/"nox_v3_supervisor.py"
       if supervisor.is_file():
        status["supervisor"]=run(["python3",str(supervisor),"--node",node],20)
     else:
      status["state"]="HOLD_IDLE_RESTART_GPU_OR_CHILD_OWNED"
      status["gpu_owners"]=owners;status["children"]=children
    except (OSError,subprocess.TimeoutExpired) as e:
     status["state"]="HOLD_IDLE_RESTART_UNVERIFIED";status["reason"]=repr(e)[:200]
  else:
   gate=S/("cutover_"+node+".json")
   try:doc=json.loads(gate.read_text())
   except (OSError,ValueError):doc={}
   if doc.get("status")!="CUTOVER_READY" or doc.get("node")!=node:
    status["state"]="HOLD_SAVEPOINT_NOT_ACCEPTED"
    # Do not bypass an unknown owner / old 100% GPU workload.
    if (BIN/"nox_v3_cutover.py").is_file():
     status["cutover"]=run(["python3",str(BIN/"nox_v3_cutover.py"),"--node",node],25)
   else:
    supervisor=BIN/"nox_v3_supervisor.py"
    if supervisor.is_file():
     status["supervisor"]=run(["python3",str(supervisor),"--node",node],20)
     status["state"]="RESTART_REQUESTED" if status["supervisor"]["exit"]==0 else "HOLD_RESTART_FAILED"
    else:status["state"]="HOLD_SUPERVISOR_MISSING"
 if improve and (BIN/"nox_improvement_loop.py").is_file():
  # Only ONE improvement writer at a time, across both Pods' shared /workspace.
  with (S/"watchdog_improvement.lock").open("a+") as lock:
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:status["improvement"]={"state":"SKIP_ALREADY_RUNNING"}
   else:status["improvement"]=run(["python3",str(BIN/"nox_improvement_loop.py")],20)
 try:
  sm=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
     "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=6)
  status["gpu"]=sm.stdout.strip() if sm.returncode==0 else "UNAVAILABLE"
 except (OSError,subprocess.TimeoutExpired):status["gpu"]="UNAVAILABLE"
 for key,path in (("v3_progress",S/("orchestrator_status_"+node+".json")),
                  ("teacher_progress",S/"status.json"),
                  ("neural_training",R/"dispatcher/a40_full_parameter/progress.json")):
  if path.is_file():
   try:
    d=json.loads(path.read_text(encoding="utf-8"))
    status[key]=({k:d.get(k) for k in ("utc","status","stage","steps_executed_this_cycle","cycle_progress_percent","optimizer_steps","teacher_batches") if k in d}
                 if key!="teacher_progress" else {"utc":d.get("utc"),"teacher_names":list(d.get("teachers",{}))})
   except (OSError,ValueError):status[key]={"status":"HOLD_UNREADABLE"}
 atomic(S/("watchdog_10s_"+node+".json"),status)
 print(json.dumps(status,ensure_ascii=False),flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument("--node",required=True,choices=["A40","A5000"])
 a=p.parse_args();S.mkdir(parents=True,exist_ok=True)
 with (S/("watchdog_10s_"+a.node+".lock")).open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   print("NOX_10S_WATCHDOG_ALREADY_RUNNING_"+a.node,flush=True);return
  counter=0
  while True:
   try:tick(a.node,counter%3==0)
   except Exception as e:
    atomic(S/("watchdog_10s_"+a.node+".json"),
       {"node":a.node,"utc":utc(),"state":"HOLD_WATCHDOG_EXCEPTION",
       "error":type(e).__name__+":"+str(e)[:200]})
   counter+=1;time.sleep(60)
if __name__=="__main__":main()
