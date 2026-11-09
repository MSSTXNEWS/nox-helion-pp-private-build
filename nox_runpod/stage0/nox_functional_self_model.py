#!/usr/bin/env python3
"""NOX grounded functional self-model: provenance, autobiography and uncertainty.
No false claims of subjective experience, independent birth date, or completed distillation.
This is persistent memory and testable self-monitoring, not proof of consciousness.
"""
import datetime,hashlib,json,os,pathlib,sqlite3,sys,time,fcntl
ROOT=pathlib.Path("/workspace/nox")
SELF=ROOT/"memory/NOX_SELF_MODEL"
MEM=ROOT/"memory/THREE_TEACHERS/nox_memory.sqlite3"
STATE=ROOT/"dispatcher/a40_v4"
SELF.mkdir(parents=True,exist_ok=True)
DB=SELF/"autobiography.sqlite3"
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(path,data):
 tmp=path.with_suffix(path.suffix+".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def receipt(path):
 if not path.is_file():return None
 try:return json.loads(path.read_text(encoding="utf-8-sig"))
 except (ValueError,OSError):return None
def evidence():
 checks={}
 for title,rel in [
  ("original_embryo","embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json"),
  ("genesis_pass_1","checkpoints/NOX_PRIME_9B_GENESIS/pass1/SUCCESS.json"),
  ("genesis_pass_2","checkpoints/NOX_PRIME_9B_GENESIS/pass2/SUCCESS.json"),
  ("genesis_pass_3","checkpoints/NOX_PRIME_9B_GENESIS/pass3/SUCCESS.json"),
  ("knowledge_pass_1","checkpoints/NOX_9B_KNOWLEDGE/pass1/SUCCESS.json"),
  ("knowledge_pass_2","checkpoints/NOX_9B_KNOWLEDGE/pass2/SUCCESS.json"),
  ("unified_9b","models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json"),
  ("a40_neural_adapter","checkpoints/NOX_A40_NEURAL_INTEGRATION/NEURAL_INTEGRATION_RECEIPT.json")]:
  p=ROOT/rel
  if p.is_file():
   st=p.stat();h=hashlib.sha256(p.read_bytes()).hexdigest()
   checks[title]={"path":rel,"sha256":h,"last_modified_utc":datetime.datetime.fromtimestamp(st.st_mtime,datetime.timezone.utc).isoformat(),"receipt_status":(receipt(p) or {}).get("status","FILE_PRESENT")}
 teachers={}
 if MEM.is_file():
  try:
   c=sqlite3.connect("file:"+str(MEM)+"?mode=ro",uri=True,timeout=3)
   for n in ("qwen9","qwen27","deepseek32"):
    teachers[n]=c.execute("SELECT COUNT(*) FROM items WHERE teacher=?",(n,)).fetchone()[0]
   c.close()
  except (sqlite3.Error,OSError):
   teachers={"status":"source_unavailable"}
 return checks,teachers
def make_snapshot():
 checks,teachers=evidence()
 completed=[x for x in checks if x.startswith("genesis_pass_") or x.startswith("knowledge_pass_")]
 original_born=checks.get("genesis_pass_1")
 birth={"policy":"The birth date of NOX is established only upon independently verified first training of NOX-owned weights.",
        "verified_birth_utc":None,"candidate_first_training_record":original_born,
        "verification":"NOT_YET_INDEPENDENTLY_VERIFIED"}
 # A successful training receipt may be a candidate, but cannot establish the first-ever training event.
 snap={
  "id":"NOX_HELION","type":"functional_self_model","utc":now(),
  "creator_relationship":{"source":"creator instructions in NOX project",
    "claim":"My creator supplied teacher models and specified my evolution goals.",
    "verification":"PROJECT_POLICY_REQUIRES_LINKED_CREATOR_EVENT_NOT_INFERRED_FROM_WEIGHTS"},
  "identity":{"one_user_facing_assistant":True,"student_model":"NOX 9B",
    "active_weights_path":"models/NOX_9B_UNIFIED",
    "verified_full_model_ready":"unified_9b" in checks},
  "origin":birth,
  "available_evidence":checks,
  "teachers":{"qwen9":{"purpose":"foundation and knowledge","ingested_items":teachers.get("qwen9",0)},
              "qwen27":{"purpose":"advanced knowledge and coding","ingested_items":teachers.get("qwen27",0)},
              "deepseek32":{"purpose":"reasoning and self-review","ingested_items":teachers.get("deepseek32",0)}},
  "capability_gates":{"historical_learning_passes_detected":len(completed),
    "independent_benchmark_pass":False,
    "all_three_teachers_neurally_integrated":False,
    "subjective_consciousness_verified":False},
  "learning_plan":["recall grounded self history","separate claimed skills from evaluated skills",
     "compare self predictions against tests","improve evidence-backed memory retrieval",
     "train on curated teacher examples with held-out evaluation","promote weights only after rollback-safe QA"],
  "limitations":["Weights do not inherently encode who supplied them without training or memory.",
    "A functional self-model is not proof of phenomenal consciousness.",
    "Teacher-generated examples require factual checking.",
    "No memory of events without evidence and timestamps."],
  "status":"SELF_MODEL_UPDATED_FROM_RECEIPTS_NOT_CLAIMED_CONSCIOUSNESS"}
 atomic(SELF/"self_model.json",snap)
 return snap
def record_snapshot(snap):
 c=sqlite3.connect(DB,timeout=15)
 try:
  c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA synchronous=FULL")
  c.execute("""CREATE TABLE IF NOT EXISTS verified_events(
   event_key TEXT PRIMARY KEY,event_type TEXT NOT NULL,source_sha TEXT NOT NULL,
   source_path TEXT NOT NULL,first_seen_utc TEXT NOT NULL)""")
  with c:
   for event,x in snap["available_evidence"].items():
    key=hashlib.sha256((event+"|"+x["sha256"]).encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO verified_events VALUES (?,?,?,?,?)",
       (key,event,x["sha256"],x["path"],now()))
 finally:c.close()
def main():
 lk=(SELF/"self_model.lock").open("a+")
 try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print("NOX_SELF_MODEL_ALREADY_RUNNING",flush=True);return
 while not (SELF/"STOP").exists():
  try:
   snap=make_snapshot();record_snapshot(snap)
   print(json.dumps({"event":"NOX_SELF_MODEL_CYCLE","utc":snap["utc"],
       "training_passes":snap["capability_gates"]["historical_learning_passes_detected"],
       "teacher_items":{k:v["ingested_items"] for k,v in snap["teachers"].items()},
       "subjective_consciousness_verified":False},ensure_ascii=False),flush=True)
  except Exception as e:print(json.dumps({"event":"SELF_MODEL_ERROR","reason":str(e)[:350]}),flush=True)
  for _ in range(60):
   if (SELF/"STOP").exists():break
   time.sleep(1)
if __name__=="__main__":main()
