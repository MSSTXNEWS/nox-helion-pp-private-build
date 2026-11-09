#!/usr/bin/env python3
"""NOX resource dispatcher: prioritize existing training and fill safe spare compute.
No dummy GPU work. No extra full 9B copies beyond one independently checkpointed auxiliary.
Never stop the pod, rewrite weights, or represent GPU % as training progress.
"""
import csv,datetime,fcntl,hashlib,json,os,pathlib,signal,subprocess,sys,time
ROOT=pathlib.Path("/workspace/nox")
LOG=ROOT/"logs"
TOOLS=ROOT/"tools"
STATE=ROOT/"dispatcher"
LOG.mkdir(parents=True,exist_ok=True);STATE.mkdir(parents=True,exist_ok=True)
LOCK=STATE/"dispatcher.lock"
HISTORY=STATE/"decisions.jsonl"
STOP=STATE/"STOP"
STAGE1=ROOT/"checkpoints/NOX_PRIME_9B_GENESIS"
AUX=ROOT/"checkpoints/NOX_9B_PARALLEL_TECH"
STAGE2=ROOT/"checkpoints/NOX_9B_KNOWLEDGE"
SOURCE=ROOT/"distillation"
pidfile=LOG/"nox_parallel_9b_lane.pid"
shutdown=False
def stop(*_):
 global shutdown
 shutdown=True
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
def record(event,**data):
 obj={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"event":event,**data}
 with HISTORY.open("a",encoding="utf-8") as f:
  f.write(json.dumps(obj,ensure_ascii=False)+"\n");f.flush()
 print(json.dumps(obj,ensure_ascii=False),flush=True)
def gpu():
 result=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=12,check=True)
 row=next(csv.reader(result.stdout.splitlines()))
 return {"util":int(row[0].strip()),"used_mib":int(row[1].strip()),
         "total_mib":int(row[2].strip()),"temp_c":int(row[3].strip())}
def processes():
 r=subprocess.run(["ps","-eo","pid,args"],text=True,capture_output=True,timeout=8,check=True)
 active=[]
 for line in r.stdout.splitlines()[1:]:
  try:pid,cmd=line.strip().split(None,1)
  except ValueError:continue
  if any(x in cmd for x in ("nox_prime_9b.py","nox_parallel_9b_lane.py",
       "nox_knowledge_extended.py","nox_9b_knowledge_stage2.py")) and "resource_dispatcher.py" not in cmd:
   if "grep" not in cmd and "pgrep" not in cmd:active.append({"pid":int(pid),"cmd":cmd[:180]})
 return active
def stage_pass_count(path):
 return len(list(path.glob("pass*/SUCCESS.json")))
def corpus_index():
 """CPU-only dedup and index, non-destructive; never rewrite user's teacher corpus."""
 files=list(SOURCE.glob("*.jsonl"))
 out={"files":[],"lines":0,"unique_sha256":0}
 hashes=set()
 for file in files[:40]:
  try:
   count=0
   with file.open("rb") as f:
    for line in f:
     if not line.strip():continue
     count+=1
     hashes.add(hashlib.sha256(line).digest())
   out["files"].append({"path":str(file),"records":count})
   out["lines"]+=count
  except OSError as ex:out["files"].append({"path":str(file),"error":str(ex)[:120]})
 out["unique_sha256"]=len(hashes)
 tmp=STATE/"corpus_index.tmp.json";tmp.write_text(json.dumps(out,indent=2),encoding="utf-8")
 tmp.replace(STATE/"corpus_index.json")
 return out
def start_aux():
 """Start via the saved, verified launcher; never spawn an unrecognized command."""
 launcher=TOOLS/"start_parallel_9b_lane.sh"
 if not launcher.is_file():return "aux_launcher_missing"
 # Avoid second copy if the queued stage2 has begun or auxiliary result already exists.
 if (AUX/"parallel_result.json").is_file():return "aux_already_completed"
 if (AUX/"STOP_AFTER_CURRENT_PASS").exists():return "aux_stop_requested"
 if pidfile.is_file():
  try:
   p=int(pidfile.read_text().strip())
   os.kill(p,0)
   return "aux_pid_running"
  except (ValueError,ProcessLookupError,PermissionError):pass
 proc=subprocess.Popen(["bash",str(launcher)],stdin=subprocess.DEVNULL,
                       stdout=open(LOG/"NOX_RESOURCE_DISPATCH.log","a"),
                       stderr=subprocess.STDOUT,start_new_session=True,
                       cwd=str(ROOT))
 return f"aux_launcher_spawned_pid_{proc.pid}"
def main():
 handle=LOCK.open("a+")
 try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  print("NOX_DISPATCHER_ALREADY_RUNNING",flush=True);return
 record("DISPATCHER_STARTED",policy="productive workload only, no dummy GPU stress")
 consecutive=0;aux_attempted=False;next_index=0
 max_age=12*3600
 started=time.monotonic()
 while not shutdown and not STOP.exists() and time.monotonic()-started<max_age:
  try:
   g=gpu();procs=processes()
   main_active=any("nox_prime_9b.py" in p["cmd"] for p in procs)
   aux_active=any("nox_parallel_9b_lane.py" in p["cmd"] for p in procs)
   knowledge_active=any(("nox_knowledge_extended.py" in p["cmd"] or "nox_9b_knowledge_stage2.py" in p["cmd"]) for p in procs)
   free=g["total_mib"]-g["used_mib"]
   enough_room=free>=10240 and g["used_mib"]<=12500
   safe=g["temp_c"]<78
   underutilized=g["util"]<65
   consecutive=consecutive+1 if (main_active and not aux_active and not knowledge_active and underutilized and enough_room and safe) else 0
   note="observe"
   if not safe:note="HOT_GPU_NO_NEW_WORK"
   elif not enough_room:note="VRAM_RESERVED_FOR_TRAINING"
   elif knowledge_active:note="KNOWLEDGE_TRAINING_HAS_PRIORITY"
   elif not main_active:note="NO_PRIMARY_GPU_TRAINER_ACTIVE"
   elif aux_active:note="BOTH_LANES_ACTIVE"
   if consecutive>=3 and not aux_attempted:
    note=start_aux();aux_attempted=True
    record("AUX_ACTION",action=note)
   record("RESOURCE_SAMPLE",**g,free_mib=free,primary_active=main_active,
     secondary_active=aux_active,knowledge_active=knowledge_active,
     primary_passes=stage_pass_count(STAGE1),parallel_passes=stage_pass_count(AUX),
     knowledge_passes=stage_pass_count(STAGE2),decision=note)
   if time.monotonic()>=next_index:
    stats=corpus_index()
    record("CPU_CORPUS_INDEX",files=len(stats["files"]),records=stats["lines"],
           unique=stats["unique_sha256"])
    next_index=time.monotonic()+900
  except Exception as ex:record("DISPATCHER_NONFATAL_ERROR",reason=str(ex)[:350])
  for _ in range(45):
   if shutdown or STOP.exists():break
   time.sleep(1)
 record("DISPATCHER_EXITED",reason="stop_signal_or_budget",no_gpu_shutdown=True)
if __name__=="__main__":main()
