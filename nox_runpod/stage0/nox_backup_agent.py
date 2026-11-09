#!/usr/bin/env python3
"""NOX backup agent: inventory cloud progress and prune only verified safe disposable files.
No active model, checkpoint, corpus, memory, donor, or incomplete file is ever removed.
Controlled by local Windows backup watcher; RunPod never requires the PC to stay online.
"""
import argparse,datetime,hashlib,json,os,pathlib,re,sys,time
ROOT=pathlib.Path("/workspace/nox").resolve()
INCLUDE=("checkpoints","distillation","memory","logs","embryo","dispatcher","models")
SKIP_DIRS={".git","__pycache__",".venv","venv","node_modules","site-packages",".cache",".locks"}
BACKUP_MAX_BYTES=12*1024**3
def checksum(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
 return h.hexdigest()
def safe_path(relative):
 if not isinstance(relative,str) or not relative or "\x00" in relative:raise ValueError("Bad path")
 p=(ROOT/relative).resolve()
 if not p.is_relative_to(ROOT) or not p.is_file() or p.is_symlink():raise ValueError("Unsafe file")
 return p
def files():
 for base in INCLUDE:
  folder=ROOT/base
  if not folder.is_dir():continue
  for dirpath,dirs,names in os.walk(folder,followlinks=False):
   dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not (pathlib.Path(dirpath)/d).is_symlink()]
   for name in names:
    p=pathlib.Path(dirpath)/name
    if not p.is_file() or p.is_symlink():continue
    try:
     st=p.stat()
     if st.st_size>BACKUP_MAX_BYTES:continue
     yield p,st
def inventory():
 result=[]
 for p,st in files():
  rel=p.relative_to(ROOT).as_posix()
  # Include active files for incremental backup, but never delete live ones.
  result.append({"path":rel,"bytes":st.st_size,"mtime_ns":st.st_mtime_ns})
 print(json.dumps({"root":str(ROOT),"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "entries":result},ensure_ascii=False,separators=(",",":")))
def hashfile(arg):
 p=safe_path(arg)
 before=p.stat()
 h=checksum(p)
 after=p.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
  raise RuntimeError("File changed during hash")
 print(json.dumps({"path":p.relative_to(ROOT).as_posix(),"bytes":after.st_size,
  "mtime_ns":after.st_mtime_ns,"sha256":h},separators=(",",":")))
def cleanup_cache():
 """Safe cache-only cleanup. Never touches model/checkpoint files or active downloads."""
 import shutil,subprocess
 candidates=[
   ROOT/"cache/pip",ROOT/"cache/torch_extensions",
   ROOT/"tmp/old",ROOT/".cache/pip",
   pathlib.Path("/root/.cache/pip"),
 ]
 summary=[]
 for candidate in candidates:
  if not candidate.is_dir() or candidate.is_symlink():continue
  # Cache may be actively written; remove only individual old regular files
  # and skip any file with an open descriptor.
  for path in candidate.rglob("*"):
   if not path.is_file() or path.is_symlink():continue
   try:
    st=path.stat()
    if time.time()-st.st_mtime<86400:continue
    if subprocess.run(["fuser","-s",str(path)],stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,timeout=2).returncode==0:continue
    bytes_=st.st_size
    path.unlink()
    summary.append({"path":str(path),"bytes":bytes_})
   except (OSError,subprocess.TimeoutExpired):continue
 print(json.dumps({"event":"SAFE_CACHE_CLEAN","count":len(summary),
   "freed_bytes":sum(x["bytes"] for x in summary),
   "scope":"old disposable cache files only","no_model_or_checkpoint_deletion":True}))
def prune(arg,expected):
 p=safe_path(arg)
 relative=p.relative_to(ROOT).as_posix()
 # Only rotated logs older than 24h can be pruned. Never active logs.
 if not re.fullmatch(r"logs/[A-Za-z0-9_.-]+\.(?:log\.\d+|log\.gz|old\.log|bak)",relative):
  raise RuntimeError("Not an allowlisted disposable rotated log: "+relative)
 before=p.stat()
 if time.time()-before.st_mtime < 86400:
  raise RuntimeError("Rotated log is not yet 24h old")
 if checksum(p)!=expected:raise RuntimeError("Cloud file no longer matches verified Windows copy")
 after=p.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
  raise RuntimeError("Rotated log changed before deletion")
 p.unlink()
 print(json.dumps({"deleted":relative,"bytes":before.st_size}))
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("action",choices=("inventory","hash","prune","cleanup-cache"))
 ap.add_argument("--path")
 ap.add_argument("--sha256")
 a=ap.parse_args()
 if a.action=="inventory":inventory()
 elif a.action=="cleanup-cache":cleanup_cache()
 elif a.action=="hash":hashfile(a.path)
 else:
  if not re.fullmatch("[a-f0-9]{64}",a.sha256 or ""):raise RuntimeError("Bad checksum")
  prune(a.path,a.sha256)
if __name__=="__main__":main()
