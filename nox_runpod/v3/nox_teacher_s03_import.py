#!/usr/bin/env python3
"""V3 verified-provenance GGUF outputs -> canonical S03, idempotent, no fake quality.
Runs only on the shared /workspace. No new DB, no unlabelled teacher swaps.
"""
import datetime,fcntl,hashlib,json,os,pathlib,sqlite3,sys
ROOT=pathlib.Path("/workspace/nox")
D=ROOT/"distillation"; S=ROOT/"dispatcher/nox_v3"
DB=ROOT/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
SOURCES={
 "Qwen3.5-9B":("NOX_V3_QWEN9B_TEACHER.jsonl","Qwen3.5-9B"),
 "Qwen3.5-27B":("NOX_V3_QWEN27B_TEACHER.jsonl","Qwen3.5-27B"),
 "DeepSeek-R1-Distill-Qwen-32B":("NOX_V3_DEEPSEEK32B_TEACHER.jsonl","DeepSeek-R1-Distill-Qwen-32B")
}
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 S.mkdir(parents=True,exist_ok=True)
 with (S/"v3_s03_import.lock").open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   print("NOX_S03_V3_IMPORT_ALREADY_RUNNING",flush=True);return
  if not DB.is_file():
   print("HOLD_CANONICAL_S03_MISSING",flush=True);return
  con=sqlite3.connect(str(DB),timeout=30)
  con.execute("PRAGMA busy_timeout=30000")
  required={"source_id","content_sha","teacher","source_file","content","topic","received_utc","created_utc","quality"}
  cols={row[1] for row in con.execute("PRAGMA table_info(knowledge)")}
  if cols!=required:raise RuntimeError("HOLD_S03_SCHEMA_NOT_EXPECTED")
  new=0;rejected=0;seen=0
  for teacher,(filename,dirname) in SOURCES.items():
   file=D/filename
   proof=ROOT/"teachers"/dirname/"nox_teacher_proof.json"
   if not file.is_file() or not proof.is_file():continue
   data=json.loads(proof.read_text())
   if data.get("teacher")!=teacher or data.get("status")!="SHA256_VERIFIED_SHARED":
    print("HOLD_TEACHER_PROVENANCE",teacher,flush=True);continue
   expected=data.get("sha256")
   if not isinstance(expected,str) or len(expected)!=64:continue
   with file.open(encoding="utf-8",errors="replace") as f:
    for line in f:
     if len(line)>500000:rejected+=1;continue
     try:
      row=json.loads(line)
      if not isinstance(row,dict) or row.get("teacher")!=teacher or row.get("model_sha256")!=expected:
       rejected+=1;continue
      text=row.get("text")
      if not isinstance(text,str) or len(text)<100 or len(text)>4000:
       rejected+=1;continue
      content_sha=hashlib.sha256(text.encode()).hexdigest()
      if row.get("content_sha")!=content_sha or not isinstance(row.get("id"),str):
       rejected+=1;continue
      sid=hashlib.sha256((filename+"|"+row["id"]+"|"+content_sha).encode()).hexdigest()
      seen+=1
      cur=con.execute("INSERT OR IGNORE INTO knowledge (source_id,content_sha,teacher,source_file,content,topic,received_utc,created_utc,quality) VALUES (?,?,?,?,?,?,?,?,?)",
       (sid,content_sha,teacher,filename,text,str(row.get("task_id",""))[:100],
        utc(),str(row.get("created_at") or "")[:70],"V3_VERIFIED_PROVENANCE_TEXT_NOT_FACT_CHECKED"))
      new+=int(cur.rowcount==1)
     except (ValueError,TypeError,KeyError,sqlite3.Error):rejected+=1
  con.commit()
  counts=dict(con.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher").fetchall())
  con.close()
  print(json.dumps({"status":"S03_V3_IMPORT_COMMITTED","utc":utc(),"new":new,"seen":seen,
    "rejected":rejected,"teachers":counts,"all_teacher_weights_absorbed":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
