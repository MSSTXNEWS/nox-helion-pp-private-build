#!/usr/bin/env python3
"""Request safe immediate NOX V3 work, without restarting RunPod containers.

Conservatively terminates only obsolete A40 legacy script processes after
graceful STOP; never kills full-parameter trainer, teacher server or unknown
GPU owner. Verification receipts are honest; best effort for actual compute.
"""
import argparse,datetime,json,os,pathlib,signal,subprocess,time
R=pathlib.Path("/workspace/nox");S=R/"dispatcher/nox_v3";BIN=S/"bin"
def argv(pid):
 try:return [x.decode(errors="replace") for x in (pathlib.Path("/proc")/str(pid)/"cmdline").read_bytes().split(b"\0") if x]
 except OSError:return []
def processes():
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdigit():continue
  a=argv(int(p.name))
  if a:yield int(p.name),a
def gpuowners():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=10)
 if p.returncode:return None
 return {int(x.strip()) for x in p.stdout.splitlines() if x.strip().isdigit()}
def execx(args,seconds=20):
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=seconds)
  return {"exit":p.returncode,"output":(p.stdout+p.stderr)[-1200:]}
 except (OSError,subprocess.TimeoutExpired) as e:return {"exit":124,"output":str(e)[:200]}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--node",required=True,choices=["A40","A5000"]);a=ap.parse_args()
 status={"node":a.node,"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"stop_pod":False,"delete_data":False}
 # A40 legacy GPU job is the known blocker; full optimizer stays protected.
 if a.node=="A40":
  old="a40_cuda_distillation_direct.py";targets=[]
  for pid,cmd in processes():
   if any(pathlib.Path(x).name==old for x in cmd[1:]):targets.append(pid)
  status["legacy_targets"]=targets
  if targets:
   marker=R/"dispatcher/a40_direct/STOP";marker.parent.mkdir(parents=True,exist_ok=True);marker.touch()
   for pid in targets:
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:pass
   time.sleep(4)
   status["legacy_remaining"]=[pid for pid in targets if argv(pid)]
   if status["legacy_remaining"]:
    status["state"]="HOLD_LEGACY_PROCESS_STILL_EXITING"
    print(json.dumps(status,ensure_ascii=False),flush=True);return
 else:
  status["legacy_targets"]=[]
 owners=gpuowners()
 status["gpu_owners"]=sorted(owners) if owners is not None else None
 if owners is None:
  status["state"]="HOLD_GPU_TELEMETRY";print(json.dumps(status),flush=True);return
 if a.node=="A5000" and owners:
  status["state"]="GPU_BUSY_EXISTING_TASK_PRESERVED"
 elif owners:
  status["state"]="HOLD_GPU_BUSY_NO_DOUBLE_OWNER"
 else:
  gate=S/("cutover_"+a.node+".json")
  try:receipt=json.loads(gate.read_text())
  except (OSError,ValueError):receipt={}
  if receipt.get("status")!="CUTOVER_READY":
   status["cutover"]=execx(["python3",str(BIN/"nox_v3_cutover.py"),"--node",a.node])
  status["activate"]=execx(["python3",str(BIN/"nox_activate_idle_v3.py"),"--node",a.node])
  status["supervisor"]=execx(["python3",str(BIN/"nox_v3_supervisor.py"),"--node",a.node])
  status["state"]="DISPATCHER_START_REQUESTED"
 for label,p in (("orchestrator",S/("orchestrator_status_"+a.node+".json")),
                 ("training",R/"dispatcher/a40_full_parameter/progress.json")):
  try:
   t=json.loads(p.read_text());status[label]={k:t.get(k) for k in ("utc","status","stage","steps_executed_this_cycle","teacher_batches","reason") if k in t}
  except (OSError,ValueError):status[label]={"state":"NO_VERIFIED_STATUS"}
 try:
  p=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
  status["gpu"]=p.stdout.strip() if p.returncode==0 else "HOLD_SENSOR"
 except (OSError,subprocess.TimeoutExpired):status["gpu"]="HOLD_SENSOR"
 print(json.dumps(status,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
