#!/usr/bin/env python3
"""NOX supervisor: restart only the V3 dispatcher on an accepted node.

No Pod/container restart, no terminating training, no cleaning old data.
Preserve ongoing process if ownership cannot be proven.
"""
import argparse, datetime, json, os, pathlib, subprocess, sys, time, fcntl
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/nox_v3"
BIN=S/"bin"
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def args_for(pid):
 try:return [x.decode(errors="replace") for x in (pathlib.Path("/proc")/str(pid)/"cmdline").read_bytes().split(bytes([0])) if x]
 except OSError:return []
def find(node):
 target=str(BIN/"nox_v3_dispatcher.py")
 out=[]
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdigit():continue
  argv=args_for(p.name)
  if target in argv and "--node" in argv and argv[argv.index("--node")+1:][:1]==[node]:
   out.append(int(p.name))
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument("--node",required=True,choices=["A40","A5000"])
 node=p.parse_args().node
 S.mkdir(parents=True,exist_ok=True)
 with (S/("supervisor_"+node+".lock")).open("a+") as lk:
  try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print("NOX_SUPERVISOR_ALREADY_ACTIVE",node);return
  cutover=S/("cutover_"+node+".json")
  try:gate=json.loads(cutover.read_text())
  except (OSError,ValueError):gate={}
  if gate.get("status")!="CUTOVER_READY" or gate.get("node")!=node:
   print("HOLD_SUPERVISOR_CUTOVER_INCOMPLETE",node);return
  if (S/("STOP_"+node)).exists() or (S/("HOLD_"+node)).exists():
   print("HOLD_SUPERVISOR_SAFETY_MARKER",node);return
  running=find(node)
  if len(running)==1:
   print("NOX_V3_DISPATCHER_ALIVE",node,running[0]);return
  if len(running)>1:
   print("HOLD_DISPATCHER_DUPLICATES",node,running);return
  script=BIN/"nox_v3_dispatcher.py"
  plan=S/"NOX_PRIME_V3_PLAN.json"
  if not script.is_file() or not plan.is_file():
   print("HOLD_V3_DISPATCHER_OR_PLAN_MISSING",node);return
  try:doc=json.loads(plan.read_text())
  except (OSError,ValueError):print("HOLD_V3_PLAN_INVALID");return
  if doc.get("transition",{}).get("no_loss") is not True:
   print("HOLD_UNSAFE_PLAN");return
  log=R/"logs"/("NOX_V3_"+node+".log");log.parent.mkdir(parents=True,exist_ok=True)
  with log.open("ab") as f:
   proc=subprocess.Popen(["python3","-u",str(script),"--node",node],cwd=str(R),
            stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  time.sleep(2)
  if proc.poll() is not None:
   print("HOLD_DISPATCHER_RESTART_FAILED",node,proc.returncode);return
  print("NOX_V3_DISPATCHER_RESTARTED",node,proc.pid,utc())
if __name__=="__main__":main()
