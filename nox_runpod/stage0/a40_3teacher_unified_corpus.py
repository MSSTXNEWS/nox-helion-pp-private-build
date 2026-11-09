#!/usr/bin/env python3
"""NOX 3-teacher unification manifest, source-backed memory/corpus consolidation.
NO training, adapters, or modification of model weights here. An actual
all-parameter optimizer cycle is mandatory for neural consolidation.
"""
import datetime,fcntl,hashlib,json,os,pathlib,sqlite3,sys,time
R=pathlib.Path("/workspace/nox")
M=R/"memory/NOX_UNIFIED_S03"
S=R/"dispatcher/a40_unification"
OUT=R/"distillation/NOX_3TEACHER_UNIFIED"
for x in (M,S,OUT):x.mkdir(parents=True,exist_ok=True)
DB=M/"unified_nox_knowledge.sqlite3"
TEACHERS=("Qwen3.5-9B","Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B")
STOP=S/"STOP"
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data.encode("utf-8")).hexdigest()
def atom_json(p,d):
 tmp=p.with_suffix(p.suffix+".new")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(d,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def atom_jsonl(p,records):
 tmp=p.with_suffix(p.suffix+".new")
 with tmp.open("w",encoding="utf-8") as f:
  for x in records:f.write(json.dumps(x,ensure_ascii=False)+"\n")
  f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def make():
 if not DB.is_file():
  return {"status":"HOLD_S03_DATABASE_NOT_FOUND","count":0,"teacher_counts":{}}
 with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=15) as con:
  values=con.execute("SELECT teacher,content,content_sha,source_file,received_utc,quality FROM knowledge").fetchall()
 counts={x:0 for x in TEACHERS};seen=set();train=[];holdout=[];bad=0
 for teacher,content,h,source,timestamp,quality in values:
  if teacher not in counts:continue
  if not isinstance(content,str) or len(content)<100 or len(content)>60000:bad+=1;continue
  if sha(content)!=h:bad+=1;continue
  if h in seen:continue
  seen.add(h);counts[teacher]+=1
  row={"id":h,"teacher":teacher,"text":content,"source":source,"received_utc":timestamp,
       "quality":"TEACHER_TEXT_UNVERIFIED","role":"teacher_sample"}
  (holdout if int(h[:8],16)%10==0 else train).append(row)
 atom_jsonl(OUT/"train.jsonl",train)
 atom_jsonl(OUT/"holdout.jsonl",holdout)
 full=R/"models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json"
 status=("READY_FOR_ADAPTER_FREE_FULL_PARAMETER_STUDENT_DISTILLATION"
         if min(counts.values())>=8 and len(train)>=48 and len(holdout)>=6 and full.is_file()
         else "HOLD_THREE_TEACHER_COVERAGE_OR_BASE")
 return {"status":status,"utc":now(),"teachers":counts,
         "train_samples":len(train),"holdout_samples":len(holdout),
         "bad_samples":bad,"base_full_model_receipt_present":full.is_file(),
         "neural_weight_consolidation":"NOT_PERFORMED",
         "adapters_allowed":False,
         "outputs":{"train":str(OUT/"train.jsonl"),"holdout":str(OUT/"holdout.jsonl")},
         "next_required":"ALL_PARAMETER_STUDENT_TRAINING_EVALUATION_AND_FULL_WEIGHTS_CHECKPOINT",
         "claims":"corpus is not evidence of absorbed weights"}
def main():
 lock=(S/"supervisor.lock").open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  print("NOX_3TEACHER_CONSOLIDATOR_ALREADY_RUNNING",flush=True);return
 while not STOP.exists():
  try:
   state=make()
   atom_json(S/"status.json",state)
   print(json.dumps({"event":"NOX_3TEACHER_MEMORY_CONSOLIDATION",**state},ensure_ascii=False),flush=True)
  except Exception as e:
   atom_json(S/"status.json",{"status":"ERROR","utc":now(),"reason":str(e)[:260]})
   print("NOX_3TEACHER_CONSOLIDATION_ERROR",str(e)[:250],flush=True)
  for _ in range(60):
   if STOP.exists():break
   time.sleep(1)
if __name__=="__main__":main()
