#!/usr/bin/env python3
"""NOX zero-loss backup and migration manifest. No deletion. No EXE replacement."""
import argparse, hashlib, json, os, shutil, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(os.environ.get("NOX_PORTABLE_ROOT") or Path.home()/"NOX_HELION_PORTABLE")
BACKUPS=ROOT/"migration"/"backups"
SOURCE_DIRS=("knowledge","config","training")
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as src:
  while True:
   chunk=src.read(4*1024*1024)
   if not chunk:break
   h.update(chunk)
 return h.hexdigest()
def backup():
 stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 target=BACKUPS/stamp
 target.mkdir(parents=True,exist_ok=False)
 files=[]
 for folder in SOURCE_DIRS:
  base=ROOT/folder
  if not base.is_dir():continue
  for path in base.rglob("*"):
   if path.is_symlink() or not path.is_file():continue
   if any(part in (".git","node_modules","__pycache__") for part in path.parts):continue
   relative=path.relative_to(ROOT)
   to=target/relative
   to.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(path,to)
   if path.stat().st_size!=to.stat().st_size or digest(path)!=digest(to):
    raise RuntimeError("COPY_MISMATCH:"+str(relative))
   files.append({"relative":str(relative),"bytes":to.stat().st_size,"sha256":digest(to)})
 memory=ROOT/"memory"
 if memory.is_dir():
  for db in memory.glob("*.sqlite3"):
   if db.is_symlink():continue
   to=target/"memory"/db.name
   to.parent.mkdir(parents=True,exist_ok=True)
   source=sqlite3.connect(str(db))
   dest=sqlite3.connect(str(to))
   try:
    source.backup(dest)
    result=dest.execute("PRAGMA integrity_check").fetchone()[0]
    if result!="ok":raise RuntimeError("SQLITE_BACKUP_NOT_OK:"+result)
   finally:dest.close();source.close()
   files.append({"relative":str(to.relative_to(target)),"bytes":to.stat().st_size,
                 "sha256":digest(to),"sqlite_integrity":"ok"})
 models_root=Path(os.environ.get("OLLAMA_MODELS") or Path.home()/".ollama"/"models")
 models=[]
 try:
  with urlopen("http://127.0.0.1:11434/api/tags",timeout=8) as r:
   for info in json.load(r).get("models",[]):
    models.append({"name":info.get("name"),"digest":info.get("digest"),"size":info.get("size")})
 except Exception as exc:models=[{"status":"OLLLAMA_LIST_UNAVAILABLE","error_type":type(exc).__name__}]
 manifest={"schema":"nox.portable.backup.v1","created_at":stamp,"root":str(ROOT),
   "ollama_models_root":str(models_root),"ollama_models_copied":False,
   "ollama_models":models,"files":files,
   "notice":"Other source archives, original EXE, and Ollama weights are NOT deleted or moved. Back up models separately before migration."}
 outfile=target/"MANIFEST.json"
 outfile.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
 print("NOX_ZERO_LOSS_BACKUP_OK",target,"FILES",len(files))
 print("MODEL_ROOT",models_root,"MODELS_NOT_COPIED")
def verify(path):
 obj=json.loads((path/"MANIFEST.json").read_text(encoding="utf-8"))
 for f in obj["files"]:
  file=path/f["relative"]
  if not file.is_file() or file.stat().st_size!=f["bytes"] or digest(file)!=f["sha256"]:
   raise RuntimeError("BACKUP_FAILED_SHA:"+f["relative"])
 print("NOX_BACKUP_READBACK_OK",path,len(obj["files"]))
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=("backup","verify"))
 p.add_argument("--path",type=Path)
 a=p.parse_args()
 if a.action=="backup":backup()
 else:
  if not a.path:raise ValueError("--path required")
  verify(a.path)
