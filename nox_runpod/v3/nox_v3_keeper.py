#!/usr/bin/env python3
"""NOX V3 migration keeper. One instance/node. Graceful savepoint -> V3 dispatcher.

Never restarts Pods, kills trainers, deletes checkpoints or clears STOP/HOLD.
Uses the existing verified cutover and V3 supervisor. Tracks failures.
"""
import argparse,datetime,fcntl,json,os,pathlib,subprocess,sys,time,urllib.request
ROOT=pathlib.Path("/workspace/nox")
STATE=ROOT/"dispatcher/nox_v3"
BIN=STATE/"bin"
MASTER="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox_runpod/control/NOX_MASTER_CONTROL.json"
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(path,d):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(d,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def safe_policy():
 req=urllib.request.Request(MASTER,headers={"User-Agent":"NOX-V3-Keeper/1"})
 with urllib.request.urlopen(req,timeout=20) as f:data=f.read(32769)
 if len(data)>32768:raise RuntimeError("HOLD_MASTER_OVERSIZE")
 d=json.loads(data)
 if d.get("schema")!="nox-control-v1" or d.get("no_loss") is not True or d.get("allow_remote_delete") is not False or d.get("allow_arbitrary_shell") is not False:
  raise RuntimeError("HOLD_MASTER_UNSAFE")
 return d["revision"]
def run_one(node):
 rev=safe_policy()
 if (STATE/("STOP_"+node)).exists() or (STATE/("MANUAL_STOP_"+node)).exists():
  return {"status":"HOLD_SAFE70_OR_STOP","master_revision":rev}
 # Exact external scripts are fetched & compile checked by installer, never arbitrary code from master JSON.
 for name in ("nox_v3_cutover.py","nox_v3_supervisor.py"):
  if not (BIN/name).is_file():return {"status":"HOLD_MISSING_"+name,"master_revision":rev}
 gate=STATE/("cutover_"+node+".json")
 try:
  receipt=json.loads(gate.read_text())
 except (OSError,ValueError):receipt={}
 if receipt.get("status")!="CUTOVER_READY" or receipt.get("node")!=node:
  proc=subprocess.run(["python3",str(BIN/"nox_v3_cutover.py"),"--node",node],
   capture_output=True,text=True,timeout=45)
  if proc.returncode:
   return {"status":"HOLD_SAVEPOINT","detail":(proc.stdout+proc.stderr)[-500:],"master_revision":rev}
 proc=subprocess.run(["python3",str(BIN/"nox_v3_supervisor.py"),"--node",node],
  capture_output=True,text=True,timeout=45)
 return {"status":"SUPERVISOR_CHECK_OK" if proc.returncode==0 else "HOLD_SUPERVISOR",
         "detail":(proc.stdout+proc.stderr)[-500:],"master_revision":rev}
def main():
 a=argparse.ArgumentParser();a.add_argument("--node",choices=("A40","A5000"),required=True)
 args=a.parse_args();STATE.mkdir(parents=True,exist_ok=True)
 with (STATE/("keeper_"+args.node+".lock")).open("a+") as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   print("NOX_V3_KEEPER_ALREADY_RUNNING",args.node,flush=True);return
  while True:
   try:state=run_one(args.node)
   except Exception as e:state={"status":"HOLD_KEEPER_EXCEPTION","detail":type(e).__name__+":"+str(e)[:220]}
   state.update({"node":args.node,"utc":stamp()})
   write(STATE/("keeper_"+args.node+".json"),state)
   print(json.dumps(state,ensure_ascii=False),flush=True)
   time.sleep(180)
if __name__=="__main__":main()
