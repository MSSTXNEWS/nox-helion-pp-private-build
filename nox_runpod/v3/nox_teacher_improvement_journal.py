#!/usr/bin/env python3
"""NOX teacher evidence and bounded self-improvement journal, all three teachers.

Read-only on weights, SQLite and generated teacher examples. Append-only evidence
on shared /workspace; no fake PASS or raw model merging. Rate measures since
previous sample. Repeated status emits every five minutes or when state changes.
"""
import argparse,datetime,fcntl,hashlib,json,os,pathlib,re,sqlite3,time
ROOT=pathlib.Path("/workspace/nox")
D=ROOT/"dispatcher/nox_guardian"
D.mkdir(parents=True,exist_ok=True)
TEACHERS={
 "Qwen3.5-9B":None,
 "Qwen3.5-27B":"NOX_V3_QWEN27B_TEACHER.jsonl",
 "DeepSeek-R1-Distill-Qwen-32B":"NOX_V3_DEEPSEEK32B_TEACHER.jsonl"}
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(path):
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError):return {}
def atomic(path,obj):
 t=path.with_name(path.name+".tmp")
 with t.open("w",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,path)
def counts():
 db=ROOT/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
 if not db.is_file():return {}, "HOLD_MISSING_S03"
 try:
  con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=5)
  values=dict(con.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher").fetchall())
  con.close()
  return values,"OK"
 except (sqlite3.Error,OSError) as e:return {}, "HOLD_S03_"+type(e).__name__
def file_count(path):
 if not path.is_file():return 0,0
 try:
  count=0
  with path.open(encoding="utf-8",errors="replace") as f:
   for line in f:
    try:
     rec=json.loads(line)
     if isinstance(rec,dict) and isinstance(rec.get("text"),str) and rec.get("content_sha"):count+=1
    except ValueError:pass
  return count,path.stat().st_size
 except OSError:return 0,0
def lastlog(path):
 try:
  with path.open("rb") as f:
   f.seek(0,2);size=f.tell();f.seek(max(0,size-8192))
   text=f.read().decode(errors="replace")
  return text,size
 except OSError:return "",0
def append(obj):
 chain=D/"teacher_improvement_head.json"
 previous=read(chain).get("sha256")
 obj["previous_sha256"]=previous
 raw=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))
 digest=hashlib.sha256(raw.encode()).hexdigest()
 path=D/"teacher_improvement_journal.jsonl"
 with path.open("a",encoding="utf-8") as f:
  f.write(raw+"\\n");f.flush();os.fsync(f.fileno())
 atomic(chain,{"utc":obj["utc"],"sha256":digest})
 return digest
def once():
 t=time.time();prior=read(D/"teacher_improvement_state.json")
 s03,dbstatus=counts()
 progress=read(ROOT/"dispatcher/a40_full_parameter/progress.json")
 output={"utc":utc(),"schema":"nox-teacher-improvement-v1","s03_status":dbstatus,
         "trainer":{"status":progress.get("status"),"stage":progress.get("stage"),
                    "optimizer_steps":progress.get("steps_executed_this_cycle"),
                    "loss":progress.get("last_train_loss"),
                    "checkpoint_verified":progress.get("status")=="COMPLETE_VERIFIED"},
         "teachers":{},"next_action":"ONLY_APPLY_CHANGE_ON_NEXT_BLOCK"}
 for teacher,filename in TEACHERS.items():
  examples,bytes_=file_count(ROOT/"distillation"/filename) if filename else (0,0)
  num=int(s03.get(teacher,0))
  older=prior.get("teachers",{}).get(teacher,{})
  dt=max(1.0,t-float(prior.get("epoch",t)))
  rate=round(max(0,examples-int(older.get("generated_examples",0)))*3600/dt,2)
  path=ROOT/"logs"/("NOX_V3_TEACHER_"+("27B" if "27B" in teacher else "32B")+".log")
  log,size=lastlog(path) if filename else ("",0)
  oldsize=int(older.get("log_bytes",0))
  # Ignore historical errors unless log has grown since last sample.
  recent=log if size>oldsize else ""
  errors=re.findall(r"HOLD_INFERENCE_REQUEST\s+(\w+)|HOLD_MODEL_NOT_READY|CUDA out of memory",recent,re.I)
  if "CUDA out of memory" in recent:action="HOLD_GPU_VRAM_TUNE_NEXT_BLOCK"
  elif "TimeoutError" in recent:action="REDUCE_CONCURRENT_REQUESTS_ON_NEXT_BLOCK"
  elif "HOLD_MODEL_NOT_READY" in recent:action="VERIFY_MODEL_SHA_AND_GGUF"
  elif teacher=="Qwen3.5-9B":action="REUSE_EXISTING_PROVENANCE_AND_AVOID_NEW_TEACHER_DOWNLOAD"
  elif examples==0:action="NO_VERIFIED_GPU_TEACHER_RESULTS_CHECK_LLAMA_SERVER"
  elif rate>0:action="MEASURE_HOLDOUT_BEFORE_NEXT_NEURAL_CYCLE"
  else:action="CHECK_TEACHER_SCHEDULING_AND_INPUT_GAPS"
  output["teachers"][teacher]={"generated_examples":examples if filename else None,
    "s03_knowledge_records":num,"new_examples_per_hour":rate if filename else None,
    "log_bytes":size,"last_new_error":recent[-280:] if errors else None,
    "improvement_candidate":action,"source_verified":num>0,
    "weights_neurally_absorbed":False}
 latest=D/"teacher_improvement_latest.json"
 atomic(latest,output)
 output_hash=hashlib.sha256(json.dumps(output,sort_keys=True).encode()).hexdigest()
 if output_hash!=prior.get("last_hash") or t-float(prior.get("last_journal_at",0))>=300:
  entry={"utc":output["utc"],"event":"TEACHER_IMPROVEMENT_EVALUATION",
         "trainer":output["trainer"],"teachers":output["teachers"],
         "verified_checkpoint":output["trainer"]["checkpoint_verified"]}
  digest=append(entry)
  print(json.dumps({"journal_sha256":digest,**entry},ensure_ascii=False),flush=True)
  last=t
 else:last=float(prior.get("last_journal_at",t))
 atomic(D/"teacher_improvement_state.json",{"epoch":t,"last_hash":output_hash,
         "last_journal_at":last,"teachers":output["teachers"]})
def main():
 p=argparse.ArgumentParser();p.add_argument("--once",action="store_true")
 a=p.parse_args()
 with (D/"teacher_improvement_process.lock").open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print("TEACHER_JOURNAL_ALREADY_RUNNING");return
  while True:
   try:once()
   except Exception as exc:print("HOLD_TEACHER_JOURNAL_ERROR",type(exc).__name__,str(exc)[:150],flush=True)
   if a.once:break
   time.sleep(60)
if __name__=="__main__":main()
