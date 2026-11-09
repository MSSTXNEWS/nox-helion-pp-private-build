#!/usr/bin/env python3
"""NOX S03: single durable knowledge memory for 3 teachers and local NOX progress.
CPU-only, no LoRA/PEFT, no optimizer, no full-weight merge claims.
Each iteration ingests new verified-structure teacher answers with immutable provenance.
"""
import datetime,fcntl,hashlib,json,os,pathlib,sqlite3,time,traceback
R=pathlib.Path("/workspace/nox"); D=R/"distillation"; M=R/"memory/NOX_UNIFIED_S03"
S=R/"dispatcher/a40_memory_only"; M.mkdir(parents=True,exist_ok=True);S.mkdir(parents=True,exist_ok=True)
DB=M/"unified_nox_knowledge.sqlite3";STOP=S/"STOP"
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atom(path,doc):
 tmp=path.with_suffix(path.suffix+".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(doc,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def identify(name,row):
 text=(name+" "+str(row.get("teacher",""))+" "+str(row.get("source_model",""))).lower()
 if "deepseek" in text or "qwen-32b" in text:return "DeepSeek-R1-Distill-Qwen-32B"
 if "qwen27" in text or "qwen3.5-27" in text or "27b" in text:return "Qwen3.5-27B"
 if "qwen9" in text or "qwen3.5-9" in text or "a5000" in text or "9b" in text:return "Qwen3.5-9B"
 return "UNATTRIBUTED"
def main():
 lk=(S/"controller.lock").open("a+")
 try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print("NOX_MEMORY_ALREADY_RUNNING",flush=True);return
 con=sqlite3.connect(DB,timeout=25)
 con.execute("PRAGMA journal_mode=WAL")
 con.execute("PRAGMA synchronous=FULL")
 con.execute("""CREATE TABLE IF NOT EXISTS knowledge (
 source_id TEXT PRIMARY KEY, content_sha TEXT NOT NULL, teacher TEXT NOT NULL,
 source_file TEXT NOT NULL, content TEXT NOT NULL, topic TEXT,
 received_utc TEXT NOT NULL, created_utc TEXT, quality TEXT NOT NULL)""")
 con.execute("CREATE INDEX IF NOT EXISTS idx_teacher ON knowledge(teacher)")
 con.execute("CREATE TABLE IF NOT EXISTS log (utc TEXT, kind TEXT, details TEXT)")
 print("NOX_UNIFIED_S03_STARTED",flush=True)
 while not STOP.exists():
  try:
   new=0; malformed=0
   for p in sorted(D.glob("*.jsonl")):
    if p.is_symlink() or p.stat().st_size>400_000_000:continue
    # skip derived train corpora and avoid recursively reimporting our own output
    if p.name.startswith(("NOX_A5000_CURATED_","NOX_A40_CURATED_","NOX_UNIFIED_S03_")):continue
    with p.open(encoding="utf-8",errors="replace") as f:
     for line in f:
      if len(line)>500000:malformed+=1;continue
      try:
       row=json.loads(line)
       if not isinstance(row,dict):malformed+=1;continue
       content=str(row.get("text") or "").strip()
       if len(content)<80:continue
       hashval=hashlib.sha256(content.encode()).hexdigest()
       origid=str(row.get("id") or hashval)
       sid=hashlib.sha256((p.name+"|"+origid+"|"+hashval).encode()).hexdigest()
       teacher=identify(p.name,row)
       cur=con.execute("INSERT OR IGNORE INTO knowledge VALUES (?,?,?,?,?,?,?,?,?)",
          (sid,hashval,teacher,p.name,content,str(row.get("topic") or "")[:300],
           utc(),str(row.get("created_at") or row.get("utc") or "")[:70],
           "TEACHER_TEXT_NOT_FACT_CHECKED"))
       new+=int(cur.rowcount==1)
      except (ValueError,TypeError,sqlite3.Error):malformed+=1
   con.commit()
   counts=dict(con.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher").fetchall())
   total=sum(counts.values())
   srcs=sorted(set(p[0] for p in con.execute("SELECT DISTINCT source_file FROM knowledge")))
   doc={"utc":utc(),"event":"NOX_UNIFIED_S03_SNAPSHOT","total":total,
        "new_records":new,"malformed":malformed,"teachers":counts,"sources":srcs,
        "models_may_have_changed_weights":False,"weight_merge":"NOT_PERFORMED",
        "model_consciousness":"NOT_VERIFIED",
        "shared_path":str(M),"database":str(DB),"readiness":"KNOWLEDGE_MEMORY_ONLY"}
   atom(M/"status.json",doc)
   print(json.dumps(doc,ensure_ascii=False),flush=True)
   con.execute("PRAGMA wal_checkpoint(PASSIVE)")
  except Exception as e:
   print(json.dumps({"event":"NOX_MEMORY_ERROR","error":str(e)[:250],
                     "trace":traceback.format_exc()[-500:]}),flush=True)
  for _ in range(60):
   if STOP.exists():break
   time.sleep(1)
 con.close()
if __name__=="__main__":main()
