#!/usr/bin/env python3
"""Generate review-only NOX HTML/Python candidate files using local Ollama."""
from pathlib import Path
import argparse, ast, hashlib, json, os, re, sqlite3, sys, time
from html.parser import HTMLParser
from urllib.request import Request, urlopen
root=Path(os.environ.get("NOX_PORTABLE_ROOT") or Path.home()/"NOX_HELION_PORTABLE")
out=root/"growth"/"drafts"
dbfile=root/"growth"/"drafts.sqlite3"
tasks=[
 ("d02-home","html","A cinematic D02 home screen with eight core spheres and Reduced Motion"),
 ("model-center","html","A model download and availability dashboard with accurate statuses"),
 ("memory-view","html","S03 searchable knowledge explorer with real source citations"),
 ("builder-view","html","Patch proposal review interface with diff, STOP and rollback controls"),
 ("worker-view","html","Task queue dashboard for a bounded research and coding worker"),
 ("studio-view","html","Icons, effects and reusable page template studio"),
 ("firstboot-view","html","NOX firstboot status page showing local model and SQLite readiness"),
 ("gpu-view","html","GPU learning status page; unknown load and temperature must say UNKNOWN"),
 ("settings-view","html","Privacy, models, autostart and permissions settings page"),
 ("coder-router","python","Read-only installed-Ollama model role selector for chat/coder/vision/embedding"),
 ("history-tools","python","SQLite memory search and deduplication report; no deletion"),
 ("safe-review","python","Create text-only code review notes and a patch proposal, without applying"),
 ("migration-plan","python","Verify SHA256 inventory for a portable user folder, no destructive changes")
]
class Structure(HTMLParser):
 def __init__(self):super().__init__();self.tags=set()
 def handle_starttag(self,tag,attrs):self.tags.add(tag)
def verified(kind,text):
 if kind=="python":ast.parse(text);return "PYTHON_AST_OK_NOT_EXECUTED"
 parser=Structure();parser.feed(text)
 if not {"html","body","main"}.issubset(parser.tags):raise ValueError("HTML_LAYOUT_HOLD")
 return "HTML_STRUCTURE_OK_NOT_BROWSER_TESTED"
def initialize():
 out.mkdir(parents=True,exist_ok=True)
 con=sqlite3.connect(dbfile,timeout=10)
 con.execute("PRAGMA journal_mode=WAL")
 con.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY,kind TEXT,goal TEXT,state TEXT,hash TEXT,reason TEXT)")
 if "attempts" not in [x[1] for x in con.execute("PRAGMA table_info(tasks)")]:
  con.execute("ALTER TABLE tasks ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
 with con:
  for name,kind,goal in tasks:con.execute("INSERT OR IGNORE INTO tasks VALUES(?,?,?,'PENDING',NULL,NULL)",(name,kind,goal))
 return con
def complete_one(con):
 row=con.execute("SELECT id,kind,goal,attempts FROM tasks WHERE state='PENDING' ORDER BY rowid LIMIT 1").fetchone()
 if not row:return False
 name,kind,goal,attempts=row
 if (root/"STOP").exists():raise RuntimeError("OWNER_STOP")
 with con:con.execute("UPDATE tasks SET state='RUNNING',attempts=attempts+1 WHERE id=?",(name,))
 system=("You are NOX HELION Coder. Return ONLY a complete single-file "+kind+" source. "
         "No explanations, no Markdown. For HTML include <!doctype html>, html, head, body, "
         "main and closing tags; use inline CSS and no external scripts or CDN. "
         "For Python return syntactically complete Python 3 code. No credentials, no system commands. "
         "This is a DRAFT for review, NOT installed; never invent execution results.")
 payload={"model":"qwen2.5-coder:7b","think":False,"stream":False,
          "options":{"num_ctx":4096,"num_predict":2200,"temperature":0.2},
          "messages":[{"role":"system","content":system},{"role":"user","content":goal}]}
 req=Request("http://127.0.0.1:11434/api/chat",
             data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
             headers={"Content-Type":"application/json; charset=utf-8"})
 try:
  with urlopen(req,timeout=240) as response:answer=json.load(response)["message"]["content"].strip()
  if answer.startswith(chr(96)*3):
   rows=answer.splitlines()
   if len(rows)>2 and rows[-1].strip()==chr(96)*3:answer="\n".join(rows[1:-1]).strip()
  if kind=="html":
   first=re.search(r"<!doctype html|<html\b",answer,re.I)
   if first:answer=answer[first.start():]
  if not answer:raise RuntimeError("MODEL_RETURNED_EMPTY")
  ext=".html" if kind=="html" else ".py"
  candidate=out/(name+ext)
  if candidate.exists():
   n=max(2,attempts+1)
   candidate=out/(name+"-r"+str(n)+ext)
   while candidate.exists():
    n+=1
    candidate=out/(name+"-r"+str(n)+ext)
  # Previous candidate bytes and receipts are always preserved.
  temp=candidate.with_suffix(candidate.suffix+".pending")
  temp.write_text(answer,encoding="utf-8")
  sha=hashlib.sha256(temp.read_bytes()).hexdigest()
  try:reason=verified(kind,answer);state="DRAFT_READY"
  except Exception as exc:state="DRAFT_HOLD";reason=str(exc)[:160]
  if (root/"STOP").exists():raise RuntimeError("OWNER_STOP_BEFORE_SAVE")
  os.replace(temp,candidate)
  receipt={"file":candidate.name,"sha256":sha,"validation":reason,"approved":False,"installed_in_exe":False}
  candidate.with_suffix(".receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
  with con:con.execute("UPDATE tasks SET state=?,hash=?,reason=? WHERE id=?",(state,sha,reason,name))
  print(name,state,sha[:12])
 except Exception as exc:
  with con:con.execute("UPDATE tasks SET state='HOLD',reason=? WHERE id=?",(str(exc)[:160],name))
  print(name,"HOLD",type(exc).__name__)
 return True
def main():
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=["status","once","run","resume","retry"])
 p.add_argument("--minutes",type=int,default=120)
 args=p.parse_args();con=initialize()
 if args.action=="retry":
  # Preserve the original queue and all previous errors before any retry.
  backup=dbfile.with_name("drafts-before-retry-"+time.strftime("%Y%m%d-%H%M%S")+".sqlite3")
  destination=sqlite3.connect(backup)
  try:con.backup(destination)
  finally:destination.close()
  with con:
   changed=con.execute("UPDATE tasks SET state='PENDING' WHERE state IN ('HOLD','DRAFT_HOLD') AND attempts<3").rowcount
  print("NOX_RETRY_QUEUED",changed,"QUEUE_BACKUP",backup)
 elif args.action=="resume":
  with con:con.execute("UPDATE tasks SET state='PENDING' WHERE state='RUNNING'")
 elif args.action in ("once","run"):
  deadline=time.monotonic()+min(180,max(1,args.minutes))*60
  while time.monotonic()<deadline:
   if (root/"STOP").exists() or not complete_one(con) or args.action=="once":break
   time.sleep(15)
 for state,count in con.execute("SELECT state,COUNT(*) FROM tasks GROUP BY state"):
  print(state,count)
 for name,state,tries,reason in con.execute("SELECT id,state,attempts,reason FROM tasks ORDER BY rowid"):
  print("TASK",name,state,"attempts="+str(tries),(reason or "")[:125])
 print("NOX_PROPOSALS_ONLY",out)
if __name__=="__main__":
 try:main()
 except KeyboardInterrupt:print("USER_INTERRUPTED")
 except Exception as exc:print("NOX_DRAFT_HOLD",str(exc)[:250],file=sys.stderr);sys.exit(1)
