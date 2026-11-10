#!/usr/bin/env python3
"""NOX conservative garbage collection: transient compiler/interrupted update files only.
No deletion of checkpoints, teachers, S03, weights, journals, source code or GGUF.
Never remove any path open by an active process. No backup copies created.
"""
import datetime,json,os,pathlib,stat,sys,time
ROOT=pathlib.Path("/workspace/nox")
SEARCH=[ROOT/"dispatcher",pathlib.Path("/tmp")]
NOW=time.time()
SUFFIXES=(".new",".tmp")
MIN_AGE=24*3600
SKIP_DIRS={"models","teachers","memory","checkpoints","distillation","logs","NOX_UNIFIED_S03"}
def opened():
 busy=set()
 for proc in pathlib.Path("/proc").iterdir():
  if not proc.name.isdigit():continue
  fd=proc/"fd"
  try:
   for item in fd.iterdir():
    try:busy.add(os.path.realpath(item))
    except OSError:pass
  except OSError:pass
 return busy
def main():
 busy=opened()
 removed=[];skipped=[];candidates=[]
 for base in SEARCH:
  if not base.is_dir():continue
  for path in base.rglob("*"):
   if not path.is_file() or path.is_symlink():continue
   if any(x in SKIP_DIRS for x in path.parts):continue
   if base==pathlib.Path("/tmp") and not path.name.startswith(("nox_","NOX_")):continue
   if path.name.startswith(".") and path.suffix not in SUFFIXES:continue
   if not (path.name.endswith(SUFFIXES) or
      (path.suffix==".pyc" and "__pycache__" in path.parts)):continue
   try:
    st=path.stat()
    if not stat.S_ISREG(st.st_mode):continue
    if NOW-st.st_mtime<MIN_AGE:continue
    if os.path.realpath(path) in busy:
     skipped.append({"file":str(path),"why":"OPEN_FILE"});continue
    if st.st_size>100*1024*1024:
     skipped.append({"file":str(path),"why":"OVER_100MB"});continue
    candidates.append(path)
   except OSError:continue
 for path in candidates:
  try:
   size=path.stat().st_size
   path.unlink()
   removed.append({"file":str(path),"bytes":size})
  except OSError as e:skipped.append({"file":str(path),"why":type(e).__name__})
 result={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "status":"SAFE_TEMP_CLEAN_COMPLETE","deleted_files":len(removed),
    "deleted_bytes":sum(x["bytes"] for x in removed),
    "deleted":removed,"skipped":skipped,
    "preserved":["weights","S03","teacher GGUF","checkpoints","logs","source files"]}
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
