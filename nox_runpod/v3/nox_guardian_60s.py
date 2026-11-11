#!/usr/bin/env python3
"""NOX guardian: bounded remediation, append-only event journal, 60-second checks.
Never edits source code, deletes data, kills unknown jobs or restarts Pods.
Self-improvement = measurable configuration experiments within safe envelopes.
"""
import argparse,datetime,fcntl,hashlib,json,os,pathlib,subprocess,time
R=pathlib.Path("/workspace/nox");D=R/"dispatcher";J=D/"nox_guardian";J.mkdir(parents=True,exist_ok=True)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except (ValueError,OSError):return {}
def atomic(p,data):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+".tmp")
 with t.open("w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def log(node,event,**fields):
 path=J/(node+"_journal.jsonl")
 with (J/(node+"_journal.lock")).open("a+") as lk:
  fcntl.flock(lk,fcntl.LOCK_EX)
  prev=read(J/(node+"_head.json"))
  obj={"utc":utc(),"node":node,"event":event,"previous_sha256":prev.get("sha256"),**fields}
  raw=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))
  digest=hashlib.sha256(raw.encode()).hexdigest()
  with path.open("a",encoding="utf-8") as f:f.write(raw+"\n");f.flush();os.fsync(f.fileno())
  atomic(J/(node+"_head.json"),{"sha256":digest,"utc":obj["utc"],"event":event})
  print(json.dumps({"sha256":digest,**obj},ensure_ascii=False),flush=True)
def owners():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],
   capture_output=True,text=True,timeout=12)
 if p.returncode:return None
 return [int(v.strip()) for v in p.stdout.splitlines() if v.strip().isdigit()]
def gpu():
 p=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.free",
    "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=10)
 return p.stdout.strip() if p.returncode==0 else "UNAVAILABLE"
def current_pids(suffix):
 a=[]
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdigit():continue
  try:
   cmd=[x.decode(errors="replace") for x in (p/"cmdline").read_bytes().split(b"\0") if x]
   if any(x.endswith(suffix) for x in cmd[1:]):a.append(int(p.name))
  except OSError:pass
 return a
def once(node):
 statepath=J/(node+"_state.json")
 state=read(statepath)
 if node=="A40NEW":
  status=read(D/"nox_a40new/status.json")
  running=current_pids("/nox_a40new_teacher_controller.py")
  batch=current_pids("/nox_teacher_server_batch.py")
  last=status.get("status","UNKNOWN")
  # These changes affect ONLY the NEXT megablock. Existing megablock is untouched.
  cfgpath=D/"nox_a40new/guardian_config.json"
  cfg=read(cfgpath)
  if not cfg:cfg={"parallel":3,"gpu_layers":40,"ctx":4096,"batch":50}
  logpath=R/"logs/NOX_A40NEW_TEACHERS.log"
  try:logtail=logpath.read_bytes()[-12000:].decode(errors="replace")
  except OSError:logtail=""
  failed=("HOLD_INFERENCE_REQUEST" in logtail or "CUDA out of memory" in logtail or
          "HOLD_TEACHER_SERVER_NOT_READY" in logtail)
  # Trigger only on NEW log file growth; never react repeatedly to same old error.
  try:size=logpath.stat().st_size
  except OSError:size=0
  changed=size>int(state.get("teacher_log_bytes",0))
  if changed and failed:
   old=cfg.copy()
   if "CUDA out of memory" in logtail:
    cfg["parallel"]=max(1,int(cfg["parallel"])-1)
    cfg["gpu_layers"]=max(20,int(cfg["gpu_layers"])-5)
   elif "HOLD_INFERENCE_REQUEST" in logtail:
    cfg["parallel"]=max(1,int(cfg["parallel"])-1)
   elif "HOLD_TEACHER_SERVER_NOT_READY" in logtail:
    cfg["ctx"]=max(2048,int(cfg["ctx"])//2)
   if cfg!=old:
    atomic(cfgpath,cfg);log(node,"NEXT_MEGABLOCK_CONFIG_ADAPTED",before=old,after=cfg,
                              evidence="NEW_LOG_BYTES",applies_to="NEXT_BATCH")
  # A status file can persist after a process dies; do not mistake it for live work.
  if last=="TEACHER_BATCH_RUNNING" and not batch:
   log(node,"STALE_RUNNING_STATUS_DETECTED",pid=status.get("pid"),gpu=gpu(),
       action="CONTROLLER_WILL_REQUEUE_IF_ALIVE")
  if not running and not (D/"nox_a40new/STOP").exists():
   # The guardian does not start unverified scripts; only known installed controller.
   script=pathlib.Path("/opt/nox_a40new/bin/nox_a40new_teacher_controller.py")
   if script.is_file():
    with (J/"start_A40NEW.lock").open("a+") as lk:
     fcntl.flock(lk,fcntl.LOCK_EX)
     if not current_pids("/nox_a40new_teacher_controller.py") and not owners():
      with (R/"logs/NOX_A40NEW_CONTROLLER.log").open("ab") as out:
       p=subprocess.Popen(["python3","-u",str(script)],stdout=out,
             stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
      log(node,"CONTROLLER_RESTART_REQUESTED",pid=p.pid)
  state["teacher_log_bytes"]=size
  state["status"]=last
 else:
  status=read(D/"nox_v3/orchestrator_status_A40.json")
  train=read(D/"a40_full_parameter/progress.json")
  own=owners()
  state["gpu_owners"]=own
  state["orchestrator_status"]=status.get("status")
  state["neural_status"]=train.get("status")
  if status.get("status","").startswith("HOLD") and own:
   # A compute owner is a running job, not permission to kill it.
   log(node,"HOLD_GPU_OWNER_PRESERVED",owners=own,status=status.get("status"),gpu=gpu())
  if train.get("status")=="ERROR" and train.get("utc")!=state.get("last_training_error_utc"):
   log(node,"TRAINING_FAILURE_RECORDED",stage=train.get("stage"),
       error=str(train.get("reason",""))[:300],action="NEXT_CYCLE_GUARDED")
   state["last_training_error_utc"]=train.get("utc")
 atomic(statepath,{"utc":utc(),**state})
 # Observable progress: teacher examples, optimizer steps and verified student receipt.
 progress={}
 for name,filepath in (("qwen27",R/"distillation/NOX_V3_QWEN27B_TEACHER.jsonl"),
                       ("deepseek32",R/"distillation/NOX_V3_DEEPSEEK32B_TEACHER.jsonl")):
  try:
   with filepath.open("rb") as fh:progress[name+"_examples"]=sum(1 for line in fh if line.strip())
  except OSError:progress[name+"_examples"]=None
 train_state=read(D/"a40_full_parameter/progress.json")
 progress["optimizer_steps_this_cycle"]=train_state.get("steps_executed_this_cycle")
 progress["trainer_status"]=train_state.get("status")
 progress["student_checkpoint_verified"]=train_state.get("status")=="COMPLETE_VERIFIED"
 progress["knowledge_absorbed_percent"]=None
 state["progress"]=progress
 atomic(J/(node+"_latest.json"),{"node":node,"utc":utc(),"gpu":gpu(),"status":state})
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--node",choices=["A40","A40NEW"],required=True)
 p.add_argument("--once",action="store_true")
 a=p.parse_args()
 with (J/(a.node+"_guardian_process.lock")).open("a+") as lk:
  try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print("NOX_GUARDIAN_ALREADY_RUNNING_"+a.node);return
  while True:
   try:once(a.node)
   except Exception as e:log(a.node,"GUARDIAN_EXCEPTION",error=type(e).__name__+":"+str(e)[:220])
   if a.once:break
   time.sleep(60)
if __name__=="__main__":main()
