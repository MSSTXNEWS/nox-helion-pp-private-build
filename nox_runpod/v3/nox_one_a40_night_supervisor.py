#!/usr/bin/env python3
"""Single-A40 unattended NOX distillation scheduler. GPU exclusive; no fake success.
Teacher 9B historical S03 -> 27B GGUF -> 32B GGUF, S03 import, full parameter
20-step accepted cycles only when NEW teacher records exist. 60s checks.
Never delete/stop Pods/checkpoints or kill unknown GPU jobs.
"""
import datetime,fcntl,hashlib,json,os,pathlib,subprocess,time,sqlite3
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/nox_solo"
B=pathlib.Path("/opt/nox_solo/bin")
PY=R/"prime9b-venv/bin/python"
TEACHERS=("Qwen3.5-9B","Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B")
FILES={"Qwen3.5-27B":R/"teachers/Qwen3.5-27B/Qwen3.5-27B-Q4_K_M.gguf",
       "DeepSeek-R1-Distill-Qwen-32B":R/"teachers/DeepSeek-R1-Distill-Qwen-32B/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except (OSError,ValueError):return {}
def atomic(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 tmp=p.with_name(p.name+".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(x,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def report(event,**values):
 obj={"utc":now(),"event":event,**values}
 atomic(S/"status.json",obj)
 raw=json.dumps(obj,ensure_ascii=False,sort_keys=True)
 with (S/"journal.jsonl").open("a",encoding="utf-8") as f:f.write(raw+"\n")
 print(raw,flush=True)
def gpuowners():
 try:
  p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=12)
  if p.returncode:return None
  return [int(s.strip()) for s in p.stdout.splitlines() if s.strip().isdigit()]
 except (OSError,subprocess.TimeoutExpired):return None
def s03():
 db=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
 if not db.is_file():return {}
 try:
  c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=6)
  result=dict(c.execute("select teacher,count(*) from knowledge group by teacher").fetchall())
  c.close();return result
 except (sqlite3.Error,OSError):return {}
def execute(cmd,label,limit):
 log=R/"logs"/("NOX_SOLO_"+label+".log");log.parent.mkdir(parents=True,exist_ok=True)
 with log.open("ab") as out:
  p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT)
  report("RUNNING",task=label,pid=p.pid,source="GPU_ONLY_WHERE_REQUIRED")
  started=time.monotonic()
  while p.poll() is None:
   if time.monotonic()-started>limit:
    # Do not terminate an in-flight GPU job; record the delay only.
    report("LONG_RUNNING_JOB_PRESERVED",task=label,pid=p.pid,elapsed_seconds=int(time.monotonic()-started))
   time.sleep(60)
 return p.returncode
def main():
 S.mkdir(parents=True,exist_ok=True)
 with (S/"solo.lock").open("a+") as lk:
  try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print("NOX_SOLO_ALREADY_RUNNING",flush=True);return
  cursor=0
  while True:
   try:
    if (S/"STOP").exists() or (R/"dispatcher/nox_v3/STOP_A40").exists() or (R/"dispatcher/nox_v3/HOLD_A40").exists():
     report("HOLD_STOP_MARKER");time.sleep(60);continue
    owners=gpuowners()
    if owners is None or owners:
     report("GPU_OWNER_PRESERVED",owners=owners);time.sleep(60);continue
    counts=s03()
    if not counts:
     report("HOLD_NO_S03");time.sleep(60);continue
    teacher=TEACHERS[cursor%3];cursor+=1
    if teacher=="Qwen3.5-9B":
     report("QWEN9B_EXISTING_EXAMPLES",s03_records=counts.get(teacher,0))
    else:
     model=FILES[teacher]
     proof=read(model.parent/"nox_teacher_proof.json")
     cuda=pathlib.Path("/opt/nox_primary_llama/llama.cpp/build/bin/llama-server")
     if model.is_file() and proof.get("status")=="SHA256_VERIFIED_SHARED" and proof.get("bytes")==model.stat().st_size and cuda.is_file():
      p=execute(["python3","-u",str(B/"nox_teacher_server_batch.py"),"--teacher",teacher,"--node","A40SOLO",
        "--start","0","--limit","50","--gpu-layers","40","--ctx","4096","--parallel","2"],
        "TEACHER_"+("27B" if "27B" in teacher else "32B"),5400)
      report("TEACHER_BATCH_FINISHED",teacher=teacher,exit_code=p)
     else:
      report("TEACHER_UNAVAILABLE",teacher=teacher,model_present=model.is_file(),
       source_verified=proof.get("status")=="SHA256_VERIFIED_SHARED",cuda_binary=cuda.is_file())
    importer=B/"nox_teacher_s03_import.py"
    if importer.is_file():
     result=execute(["python3",str(importer)],"S03_IMPORT",600)
     report("S03_IMPORT_FINISHED",exit_code=result,counts=s03())
    if gpuowners():
     report("HOLD_GPU_OWNER_BEFORE_TRAIN",owners=gpuowners());time.sleep(60);continue
    train=B/"a40_full_parameter_distill_cycle.py"
    if not train.is_file() or not PY.is_file():
     report("HOLD_TRAINER_MISSING");time.sleep(60);continue
    cycle="v3_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    result=execute([str(PY),"-u",str(train),"--cycle",cycle,"--steps","20"],"FULL_PARAMETER",7200)
    progress=read(R/"dispatcher/a40_full_parameter/progress.json")
    report("TRAIN_CYCLE_FINISHED",cycle=cycle,exit_code=result,
     trainer_status=progress.get("status"),steps=progress.get("steps_executed_this_cycle"),
     reason=progress.get("reason"),s03=s03())
    # A held dataset will remain HOLD until a genuine new teacher example arrives.
    time.sleep(60)
   except Exception as exc:
    report("HOLD_DISPATCHER_EXCEPTION",error=type(exc).__name__+":"+str(exc)[:200])
    time.sleep(60)
if __name__=="__main__":main()
