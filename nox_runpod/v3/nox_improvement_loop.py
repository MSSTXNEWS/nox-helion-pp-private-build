#!/usr/bin/env python3
"""NOX V3 cumulative improvement journal and adaptive teacher allocation.

Only measurable evidence. Never auto-promotes untested source or self-generated
text, never claims full absorption, and cannot restart its own trainer.
"""
import collections,datetime,hashlib,json,os,pathlib,sqlite3,sys
R=pathlib.Path("/workspace/nox"); S=R/"dispatcher/nox_v3"
LEDGER=S/"improvement_journal.jsonl"; STATUS=S/"improvement_status.json"
FULL=R/"dispatcher/a40_full_parameter/progress.json"
TEACHERS=("Qwen3.5-9B","Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B")
def read(p):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except (OSError,ValueError):return {}
def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def mem():
 db=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
 if not db.exists():return {}
 try:
  c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=5)
  try:return dict(c.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher").fetchall())
  finally:c.close()
 except sqlite3.Error:return {}
def append(data):
 S.mkdir(parents=True,exist_ok=True)
 prev="0"*64
 seen=set()
 if LEDGER.is_file():
  with LEDGER.open(encoding="utf-8") as f:
   for line in f:
    try:
     r=json.loads(line)
     if r["previous_hash"]!=prev or sha(canon({k:v for k,v in r.items() if k!="entry_hash"}))!=r["entry_hash"]:
      raise RuntimeError("HOLD_IMPROVEMENT_JOURNAL_INTEGRITY")
     prev=r["entry_hash"];seen.add(r["event_id"])
    except (ValueError,TypeError,KeyError):raise RuntimeError("HOLD_IMPROVEMENT_JOURNAL_CORRUPT")
 if data["event_id"] in seen:return False
 row={**data,"previous_hash":prev}
 row["entry_hash"]=sha(canon(row))
 with LEDGER.open("ab") as f:
  f.write(canon(row)+b"\n");f.flush();os.fsync(f.fileno())
 return True
def choose_target(totals):
 # Prefer the least-confirmed teacher, but only when that model and its GGUF
 # provenance proof are genuinely ready. Unavailable models cause HOLD.
 ready=[]
 for t in TEACHERS[1:]:
  folder=("Qwen3.5-27B" if t=="Qwen3.5-27B" else "DeepSeek-R1-Distill-Qwen-32B")
  proof=read(R/"teachers"/folder/"nox_teacher_proof.json")
  if proof.get("status")=="SHA256_VERIFIED_SHARED" and proof.get("teacher")==t:
   ready.append(t)
 if not ready:return None
 return sorted(ready,key=lambda t:(totals.get(t,0),t))[0]
def main():
 p=read(FULL); memory=mem()
 steps=p.get("steps_executed_this_cycle") or 0
 extra=p.get("extra") or {}
 counted=extra.get("optimizer_steps_by_teacher") if isinstance(extra.get("optimizer_steps_by_teacher"),dict) else {}
 valid=p.get("status")=="COMPLETE_VERIFIED" and steps>0
 event={"event_id":sha(canon({"utc":p.get("utc"),"steps":steps,"status":p.get("status")})),
   "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
   "kind":"OPTIMIZER_CYCLE_COMPLETED" if valid else "STATUS_OBSERVED",
   "trainer_status":p.get("status"),"completed_steps":steps if valid else 0,
   "optimizer_steps_by_teacher":counted if valid else {},
   "observed_loss":p.get("last_train_loss"),"observed_holdout":p.get("holdout_loss"),
   "s03_counts":memory,"proof_kind":"progress_receipt_not_independent_revalidation"}
 if p:append(event)
 target=choose_target(counted)
 status={"utc":event["utc"],"latest_trainer_status":p.get("status","UNKNOWN"),
   "last_cycle_steps":steps,"last_cycle_teacher_steps":counted,
   "s03_counts":memory,"recommended_next_teacher":target or "HOLD_NO_VERIFIED_LARGE_TEACHER",
   "next_action":"GENERATE_UNSEEN_VERIFIED_TASKS" if target else "WAIT_FOR_TEACHER_PROOF",
   "self_improvement":{"proposal":"Train only after verified teacher data; compare independent holdout and regressions",
      "automatic_source_code_promotion":False,"unverified_capability_claims":False},
   "journal":str(LEDGER),"total_knowledge_absorbed_percent":None}
 write(STATUS,status)
 print(json.dumps({"event":"NOX_IMPROVEMENT_RECORDED",**status},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
