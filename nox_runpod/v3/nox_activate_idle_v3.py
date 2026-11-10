#!/usr/bin/env python3
"""NOX V3 activation: reload ONLY idle stale V3 dispatcher, with GPU ownership proof."""
import argparse,datetime,json,os,pathlib,signal,subprocess,time,fcntl
R=pathlib.Path("/workspace/nox");S=R/"dispatcher/nox_v3";BIN=S/"bin"
def argv(pid):
 try:return [x.decode(errors="replace") for x in (pathlib.Path("/proc")/str(pid)/"cmdline").read_bytes().split(b"\0") if x]
 except OSError:return []
def pids(node):
 path=str(BIN/"nox_v3_dispatcher.py");found=[]
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdigit():continue
  a=argv(p.name)
  if path in a and "--node" in a:
   i=a.index("--node")
   if len(a)>i+1 and a[i+1]==node:found.append(int(p.name))
 return found
def owners():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=12)
 if p.returncode:raise RuntimeError("HOLD_GPU_OWNER_QUERY")
 return [int(x.strip()) for x in p.stdout.splitlines() if x.strip().isdigit()]
def descendants(pid):
 ret=[]
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdigit():continue
  try:
   stat=(p/"stat").read_text()
   if int(stat.rsplit(")",1)[1].strip().split()[1])==pid:ret.append(int(p.name))
  except (OSError,ValueError,IndexError):pass
 return ret
def read(path):
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError):return {}
def report(node,state,**kwargs):
 obj={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"node":node,"state":state,**kwargs}
 print(json.dumps(obj,ensure_ascii=False),flush=True)
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--node",required=True,choices=("A40","A5000"));a=ap.parse_args();node=a.node
 S.mkdir(parents=True,exist_ok=True)
 with (S/("activate_idle_"+node+".lock")).open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:report(node,"HOLD_ACTIVATION_IN_PROGRESS");return
  gate=read(S/("cutover_"+node+".json"))
  if gate.get("status")!="CUTOVER_READY" or gate.get("node")!=node:
   report(node,"HOLD_CUTOVER_NOT_VERIFIED");return
  if any((S/(name+"_"+node)).exists() for name in ("STOP","MANUAL_STOP","HOLD")):
   report(node,"HOLD_STOP_MARKER");return
  active=pids(node)
  if len(active)>1:
   report(node,"HOLD_DUPLICATE_DISPATCHERS",pids=active);return
  if active:
   status=read(S/("orchestrator_status_"+node+".json"))
   if not status:status=read(S/"orchestrator_status.json")
   if status.get("node")!=node or status.get("status") not in ("PREPARED_NOT_STARTED","HOLD_CUTOVER_SAVEPOINT_PENDING","HOLD_OLD_OR_FULL_GPU_OWNER_ACTIVE","HOLD_OTHER_GPU_COMPUTE_OWNER"):
    report(node,"DISPATCHER_EXISTING_NOT_IDLE",pids=active,current=status.get("status"));return
   gpu=owners();children=descendants(active[0])
   if gpu or children:
    report(node,"HOLD_GPU_OR_CHILD_OWNED",gpu_owners=gpu,children=children);return
   os.kill(active[0],signal.SIGTERM)
   for _ in range(30):
    if active[0] not in pids(node):break
    time.sleep(.1)
   if active[0] in pids(node):
    report(node,"HOLD_OLD_DISPATCHER_STILL_RUNNING");return
  supervisor=BIN/"nox_v3_supervisor.py"
  if not supervisor.is_file():
   report(node,"HOLD_SUPERVISOR_MISSING");return
  x=subprocess.run(["python3",str(supervisor),"--node",node],capture_output=True,text=True,timeout=30)
  report(node,"START_REQUESTED" if x.returncode==0 else "HOLD_SUPERVISOR",
    exit=x.returncode,details=(x.stdout+x.stderr)[-900:],pids=pids(node))
if __name__=="__main__":main()
