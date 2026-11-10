#!/usr/bin/env python3
"""NOX MEGA1 factual 3-teacher progress/ETA and SHA-chained improvement journal.

100 task quota per external teacher is a bounded *task plan*, NOT 100% absorbed
knowledge. Training speed is based only on completed steps in observed logs.
"""
import datetime,fcntl,hashlib,json,os,pathlib,sqlite3,time
R=pathlib.Path("/workspace/nox");D=R/"dispatcher/nox_v3"
OUT=D/"night_progress.json";HEAD=D/"night_progress_head.json"
TEACHERS=("Qwen3.5-9B","Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B")
FILES={"Qwen3.5-27B":"NOX_V3_QWEN27B_TEACHER.jsonl","DeepSeek-R1-Distill-Qwen-32B":"NOX_V3_DEEPSEEK32B_TEACHER.jsonl"}
def read(p):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except (ValueError,OSError):return {}
def atomic(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+".new")
 with temp.open("w",encoding="utf-8") as f:
  json.dump(obj,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
 os.replace(temp,path)
def get_s03():
 db=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
 if not db.is_file():return {}, "MISSING"
 try:
  con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=6)
  counts=dict(con.execute("select teacher,count(*) from knowledge group by teacher").fetchall())
  con.close();return counts,"OK"
 except (sqlite3.Error,OSError) as e:return {},type(e).__name__
def task_indices(file,teacher):
 if not file.is_file():return set()
 ids=set()
 try:
  with file.open(encoding="utf-8",errors="replace") as f:
   for line in f:
    try:
     x=json.loads(line);i=x.get("task_id")
     if x.get("teacher")==teacher and isinstance(i,int) and 0<=i<100 and x.get("model_sha256") and x.get("content_sha"):ids.add(i)
    except (ValueError,TypeError):pass
 except OSError:pass
 return ids
def main():
 D.mkdir(parents=True,exist_ok=True)
 with (D/"night_progress.lock").open("a+") as lk:
  fcntl.flock(lk,fcntl.LOCK_EX)
  prev=read(OUT);counts,db_state=get_s03()
  stamp=time.time()
  runtime=max(1,stamp-float(prev.get("epoch",stamp)))
  trainer=read(R/"dispatcher/a40_full_parameter/progress.json")
  accepted=read(R/"dispatcher/a40_full_parameter/last_cycle_receipt.json")
  table={}
  for name in TEACHERS:
   proof=read(R/"teachers"/name/"nox_teacher_proof.json") if name in FILES else {}
   file=R/"distillation"/FILES[name] if name in FILES else None
   ids=task_indices(file,name) if file else set()
   n=len(ids)
   before=int(prev.get("teachers",{}).get(name,{}).get("generated_tasks",0))
   rate=max(0,n-before)/runtime*3600
   eta=(100-n)/rate if rate>0 and n<100 else (0 if n==100 else None)
   verified=(proof.get("status")=="SHA256_VERIFIED_SHARED" and bool(proof.get("sha256"))) if file else None
   table[name]={"generated_tasks":n if file else None,"task_quota":100 if file else None,
      "task_plan_progress_pct":n if file else None,
      "new_tasks_per_hour":round(rate,2) if file else None,
      "task_plan_eta_hours":round(eta,2) if eta is not None else None,
      "s03_records":int(counts.get(name,0)),
      "model_provenance_verified":verified,
      "neural_weight_transfer_confirmed":bool(accepted.get("optimizer_steps_by_teacher",{}).get(name,0)),
      "full_knowledge_absorption_percent":None}
  obj={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"epoch":stamp,
       "s03_status":db_state,"teachers":table,
       "trainer":{"status":trainer.get("status"),"stage":trainer.get("stage"),
        "steps_this_cycle":trainer.get("steps_executed_this_cycle"),
        "target_steps":trainer.get("target_steps_this_cycle"),
        "step_rate_h":(trainer.get("extra") or {}).get("steps_per_hour"),
        "accepted_total_checkpoint_steps":accepted.get("steps"),
        "accepted_teacher_steps":accepted.get("optimizer_steps_by_teacher"),
        "checkpoint_saved":trainer.get("status")=="COMPLETE_VERIFIED"},
       "goal":"finish verified task plan and benchmarked student learning",
       "total_knowledge_absorbed_percent":None}
  atomic(OUT,obj)
  journal=D/"night_improvement_journal.jsonl"
  last=read(HEAD)
  summary={"utc":obj["utc"],"teachers":table,"trainer":obj["trainer"],"s03_status":db_state,
           "previous_sha256":last.get("sha256")}
  raw=json.dumps(summary,ensure_ascii=False,sort_keys=True,separators=(",",":"))
  digest=hashlib.sha256(raw.encode()).hexdigest()
  with journal.open("a",encoding="utf-8") as f:f.write(raw+"\n");f.flush();os.fsync(f.fileno())
  atomic(HEAD,{"sha256":digest,"utc":obj["utc"]})
  print(json.dumps(obj,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
