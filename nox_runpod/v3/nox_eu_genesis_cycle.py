#!/usr/bin/env python3
"""EU A40 NOX single-GPU night distillation: real teacher GPU batches, S03 and full weights.
No fake 'absorbed all'; full-weight checkpoint only, NO LoRA, NO other GPU owner killed.
"""
import datetime,fcntl,hashlib,json,os,pathlib,sqlite3,subprocess,time,signal
R=pathlib.Path("/workspace/nox")
D=pathlib.Path("/opt/nox_eu_genesis")
B=R/"dispatcher/nox_v3/bin"
STATE=R/"dispatcher/nox_eu_genesis"
STATE.mkdir(parents=True,exist_ok=True)
TEACHERS=[
 ("Qwen3.5-27B",R/"teachers/Qwen3.5-27B/Qwen3.5-27B-Q4_K_M.gguf"),
 ("DeepSeek-R1-Distill-Qwen-32B",R/"teachers/DeepSeek-R1-Distill-Qwen-32B/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf")]
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except (OSError,ValueError):return {}
def write(obj):
 obj={"utc":utc(),**obj}
 p=STATE/"status.json";t=p.with_suffix(".tmp")
 with t.open("w",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
 with (STATE/"journal.jsonl").open("a",encoding="utf-8") as f:
  f.write(json.dumps(obj,ensure_ascii=False)+"\n");f.flush()
 print(json.dumps(obj,ensure_ascii=False),flush=True)
def owners():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=12)
 if p.returncode:raise RuntimeError("GPU_OWNER_SENSOR_MISSING")
 return [int(v) for v in p.stdout.splitlines() if v.strip().isdigit()]
def work(cmd,stage,limit):
 log=R/"logs"/("NOX_EU_"+stage+".log")
 log.parent.mkdir(parents=True,exist_ok=True)
 if owners():
  write({"state":"HOLD_OTHER_GPU_OWNER","owner_pids":owners(),"stage":stage})
  return 10
 started=time.monotonic()
 with log.open("ab") as out:
  env={**os.environ,"NOX_LLAMA_CUDA_SERVER":str(D/"llama.cpp/build/bin/llama-server"),
       "PYTORCH_CUDA_ALLOC_CONF":"expandable_segments:True"}
  p=subprocess.Popen(cmd,env=env,stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,cwd=str(R))
  while p.poll() is None:
   if (STATE/"STOP").exists():
    # Respect STOP; allow at most current task to finish if training. Do not kill.
    write({"state":"STOP_REQUESTED_WAITING_FOR_SAFE_BOUNDARY","stage":stage,"pid":p.pid})
   st=read(R/"dispatcher/a40_full_parameter/progress.json")
   write({"state":"RUNNING","stage":stage,"pid":p.pid,"gpu_owners":owners(),
          "neural_steps":st.get("steps_executed_this_cycle"),"neural_status":st.get("status")})
   time.sleep(60)
 duration=time.monotonic()-started
 write({"state":"DONE" if p.returncode==0 else "HOLD_WORKER_ERROR","stage":stage,
       "exit":p.returncode,"seconds":round(duration,2),"log":str(log)})
 return p.returncode
def source_ready(name,path):
 p=read(path.parent/"nox_teacher_proof.json")
 return path.is_file() and p.get("teacher")==name and p.get("status")=="SHA256_VERIFIED_SHARED" and p.get("bytes")==path.stat().st_size
def task_set(name):
 src=R/"distillation"/("NOX_V3_QWEN27B_TEACHER.jsonl" if name=="Qwen3.5-27B" else "NOX_V3_DEEPSEEK32B_TEACHER.jsonl")
 out=set()
 try:
  with src.open(encoding="utf-8",errors="replace") as f:
   for line in f:
    try:
     obj=json.loads(line)
     if obj.get("teacher")==name and isinstance(obj.get("task_id"),int):out.add(obj["task_id"])
    except ValueError:pass
 except OSError:pass
 return out
def import_s03():
 py=B/"nox_teacher_s03_import.py"
 if not py.is_file():return
 p=subprocess.run(["python3",str(py)],capture_output=True,text=True,timeout=180)
 write({"state":"S03_IMPORT","exit":p.returncode,"message":(p.stdout+p.stderr)[-850:]})
def train_ready():
 base=R/"models/NOX_9B_UNIFIED"
 doc=read(base/"NOX_UNIFIED_RECEIPT.json")
 if not base.is_dir() or doc.get("source_repository")!="Qwen/Qwen3.5-9B":return False
 if not all((base/s.get("file","")).is_file() for s in doc.get("shards",[])):return False
 db=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
 if not db.exists():return False
 try:
  c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=8)
  n=c.execute("select count(*) from knowledge where teacher!='UNATTRIBUTED'").fetchone()[0]
  c.close()
  return n>=45
 except sqlite3.Error:return False
def main():
 with (STATE/"engine.lock").open("a+") as lk:
  try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:write({"state":"HOLD_ALREADY_ACTIVE"});return
  while not (STATE/"STOP").exists():
   try:
    pending=0
    for name,path in TEACHERS:
     if not source_ready(name,path):
      write({"state":"WAIT_TEACHER_SHA","teacher":name})
      continue
     for start in (0,50):
      done=task_set(name)
      remaining=[i for i in range(start,start+50) if i not in done]
      if not remaining:continue
      pending+=len(remaining)
      server=D/"llama.cpp/build/bin/llama-server"
      if not server.is_file():
       write({"state":"HOLD_CUDA_LLAMA_MISSING"});break
      py=B/"nox_teacher_server_batch.py"
      if not py.is_file():write({"state":"HOLD_TEACHER_CODE_MISSING"});break
      rc=work([str(D/"venv/bin/python"),"-u",str(py),"--node","A40SOLO",
         "--teacher",name,"--start",str(start),"--limit","50","--gpu-layers","38",
         "--parallel","3","--ctx","4096"],"TEACHER_"+("27B" if "27B" in name else "32B"),5400)
      import_s03()
      if rc:break
   except Exception as e:
    write({"state":"HOLD_TEACHER_LOOP","reason":type(e).__name__+":"+str(e)[:250]})
   try:
    if train_ready() and not owners():
     py=B/"a40_full_parameter_distill_cycle.py"
     if py.is_file():
      cycle="v3_eu_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
      work([str(D/"venv/bin/python"),"-u",str(py),"--cycle",cycle,"--steps","20"],"STUDENT_ALL_WEIGHTS",7200)
    else:write({"state":"WAIT_REAL_STUDENT_DATA_OR_FREE_GPU"})
   except Exception as e:write({"state":"HOLD_TRAIN_LOOP","reason":type(e).__name__+":"+str(e)[:240]})
   if pending==0:
    write({"state":"PLAN_EXHAUSTED_WAIT_NEW_VERIFIED_TEACHER_TASKS","knowledge_absorbed_percent":None})
   time.sleep(60)
 write({"state":"STOPPED_BY_USER_MARKER"})
if __name__=="__main__":main()
