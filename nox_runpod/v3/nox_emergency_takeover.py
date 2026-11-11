#!/usr/bin/env python3
"""One-shot A40/A5000 NOX V3 takeover, explicit emergency legacy process stop.

Owner-approved: interrupt ONLY exact listed stale NOX workers and supervisors.
Never stop Pod/container, delete S03/weights/checkpoints, or kill unknown owners.
No blocking source installs or downloads before the existing V3 can work.
"""
import argparse,datetime,fcntl,json,os,pathlib,signal,subprocess,sys,time
ROOT=pathlib.Path("/workspace/nox")
S=ROOT/"dispatcher/nox_v3"
BIN=S/"bin"
OLD={
 "A40":{"a40_cuda_distillation_direct.py"},
 "A5000":{"a5000_background_knowledge.py","a5000_second_cuda_distillation.py",
          "a5000_pure_distillation.py","a5000_cuda_secondary_direct.py",
          "a5000_cuda_distillation_direct.py"}
}
SUP={
 "A40":{"watchdog_supervise.sh"},
 "A5000":{"supervisor.sh"}
}
SUP_PATHS={
 "A40":{"/workspace/nox/dispatcher/a40_direct/watchdog_supervise.sh"},
 "A5000":{"/workspace/nox/dispatcher/a5000_cuda_secondary/supervisor.sh"}
}
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def cmds(pid):
 try:return [a.decode(errors="replace") for a in (pathlib.Path("/proc")/str(pid)/"cmdline").read_bytes().split(b"\0") if a]
 except OSError:return []
def processes():
 for p in pathlib.Path("/proc").iterdir():
  if p.name.isdigit():
   argv=cmds(p.name)
   if argv:yield int(p.name),argv
def model_worker(argv,node):
 return any(pathlib.Path(x).name in OLD[node] for x in argv[1:])
def legacy_supervisor(argv,node):
 return any(x in SUP_PATHS[node] for x in argv[1:])
def owners():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],
    capture_output=True,text=True,timeout=12,check=False)
 if p.returncode!=0:raise RuntimeError("GPU_OWNERS_UNAVAILABLE:"+p.stderr[-200:])
 return {int(x.strip()) for x in p.stdout.splitlines() if x.strip().isdigit()}
def atomic(p,obj):
 t=p.with_name(p.name+".new")
 with t.open("w",encoding="utf-8") as f:
  json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def cron_backup_disable(node,report):
 if not shutil_which("crontab"):report["cron"]="NO_CRONTAB";return
 p=subprocess.run(["crontab","-l"],capture_output=True,text=True,timeout=10)
 if p.returncode!=0:report["cron"]="EMPTY_OR_NO_ACCESS";return
 lines=p.stdout.splitlines()
 needles=tuple(OLD[node])+tuple(SUP_PATHS[node])
 disabled=[s for s in lines if any(n in s for n in needles) and not s.lstrip().startswith("#")]
 if not disabled:report["cron"]="NO_MATCH";return
 backup=S/("legacy_crontab_"+node+"_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".txt")
 backup.write_text(p.stdout,encoding="utf-8")
 preserved=[s for s in lines if s not in disabled]
 q=subprocess.run(["crontab","-"],input="\n".join(preserved)+"\n",text=True,capture_output=True,timeout=12)
 if q.returncode!=0:raise RuntimeError("HOLD_CRON_DISABLE_FAILED:"+q.stderr[:120])
 report["cron"]="KNOWN_OLD_DISABLED";report["cron_backup"]=str(backup)
 report["cron_disabled_entries"]=len(disabled)
def shutil_which(name):
 import shutil
 return shutil.which(name)
def signal_owned(pid,argv,node,report):
 if not (model_worker(argv,node) or legacy_supervisor(argv,node)):return
 if not cmds(pid):return
 os.kill(pid,signal.SIGTERM)
 report["sigterm"].append(pid)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--node",choices=("A40","A5000"),required=True)
 a=ap.parse_args();node=a.node
 S.mkdir(parents=True,exist_ok=True)
 with (S/("takeover_"+node+".lock")).open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print("NOX_TAKEOVER_ALREADY_IN_PROGRESS",node);return
  report={"utc":utc(),"node":node,"action":"EMERGENCY_LEGACY_HANDOFF",
          "sigterm":[],"sigkill":[],"saved_files_deleted":False,"pod_stopped":False}
  try:
   report["owners_before"]=sorted(owners())
   cron_backup_disable(node,report)
   oldmark=ROOT/("dispatcher/a40_direct/STOP" if node=="A40" else "dispatcher/a5000_cuda_secondary/STOP")
   oldmark.parent.mkdir(parents=True,exist_ok=True);oldmark.touch()
   for pid,argv in list(processes()):
    if model_worker(argv,node) or legacy_supervisor(argv,node):
     try:signal_owned(pid,argv,node,report)
     except ProcessLookupError:pass
   time.sleep(5)
   # Only same PID+EXACT old argv remains subject to previously authorized emergency SIGKILL.
   for pid,argv in list(processes()):
    if pid in report["sigterm"] and (model_worker(argv,node) or legacy_supervisor(argv,node)):
     try:os.kill(pid,signal.SIGKILL);report["sigkill"].append(pid)
     except ProcessLookupError:pass
   time.sleep(2)
   report["owners_after"]=sorted(owners())
   if report["owners_after"]:
    report["status"]="HOLD_OTHER_GPU_OWNER"
    report["unreconciled"]=[{"pid":p,"argv":" ".join(cmds(p))[:220]} for p in report["owners_after"]]
   else:
    # Do not clear current V3 STOP/HOLD markers or create fictitious receipts.
    gate=BIN/"nox_v3_cutover.py"
    sup=BIN/"nox_v3_supervisor.py"
    if not gate.is_file() or not sup.is_file():
     report["status"]="HOLD_V3_COMPONENT_MISSING"
    else:
     c=subprocess.run(["python3",str(gate),"--node",node],capture_output=True,text=True,timeout=30)
     report["cutover"]={"exit":c.returncode,"details":(c.stdout+c.stderr)[-700:]}
     if c.returncode:
      report["status"]="HOLD_CUTOVER_REJECTED"
     else:
      # Existing dispatcher is allowed to run if already present. If stale idle
      # code exists, watchdog 10s owns controlled reload.
      d=subprocess.run(["python3",str(sup),"--node",node],capture_output=True,text=True,timeout=30)
      report["supervisor"]={"exit":d.returncode,"details":(d.stdout+d.stderr)[-700:]}
      report["status"]="V3_HANDOFF_REQUESTED" if d.returncode==0 else "HOLD_V3_SUPERVISOR"
  except Exception as exc:
   report["status"]="HOLD_TAKEOVER_EXCEPTION";report["error"]=type(exc).__name__+":"+str(exc)[:300]
  report["utc_finished"]=utc()
  atomic(S/("takeover_"+node+".json"),report)
  print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
