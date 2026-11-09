#!/usr/bin/env python3
"""NOX Windows backup inventory, no deletion. Outputs one JSON row per stable file.
Only listed project directories, optional per-Pod container models.
"""
import argparse,hashlib,json,os,pathlib,time
SHARED=pathlib.Path("/workspace/nox")
CONTAINER=pathlib.Path("/opt")
DIRS={"shared":["checkpoints","models","distillation","memory","embryo","dispatcher","tools","logs"],
      "container":["nox_historical_full_weights","nox_teacher_27b","nox_teachers","nox_full_parameter_A40"]}
def paths(scope):
 root=SHARED if scope=="shared" else CONTAINER
 for folder in DIRS[scope]:
  d=root/folder
  if not d.is_dir() or d.is_symlink():continue
  for dirpath,subdirs,filenames in os.walk(d,followlinks=False):
   subdirs[:]=[x for x in subdirs if not (pathlib.Path(dirpath)/x).is_symlink()
              and x not in ("__pycache__",".cache",".git","node_modules","site-packages")]
   for name in filenames:
    p=pathlib.Path(dirpath)/name
    if not p.is_file() or p.is_symlink() or name.endswith((".noxpart",".part",".tmp",".lock")):continue
    try:st=p.stat()
    except OSError:continue
    # Avoid in-flight files without claiming that they were backed up.
    if time.time()-st.st_mtime<120:continue
    yield p,st
def secure(scope,rel):
 if not rel or "\x00" in rel:raise ValueError("unsafe path")
 root=SHARED if scope=="shared" else CONTAINER
 path=(root/rel).resolve()
 if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():raise ValueError("unsafe file")
 if pathlib.PurePosixPath(rel).parts[0] not in DIRS[scope]:raise ValueError("not in allowlist")
 return path
def filehash(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for part in iter(lambda:f.read(8*1024*1024),b""):h.update(part)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("action",choices=("inventory","hash"))
 ap.add_argument("--scope",choices=("shared","container"),required=True)
 ap.add_argument("--file")
 a=ap.parse_args()
 if a.action=="inventory":
  for path,st in paths(a.scope):
   root=SHARED if a.scope=="shared" else CONTAINER
   print(json.dumps({"relative":path.relative_to(root).as_posix(),"size":st.st_size,"mtime_ns":st.st_mtime_ns},
           ensure_ascii=False,separators=(",",":")),flush=True)
 else:
  path=secure(a.scope,a.file)
  st=path.stat();digest=filehash(path)
  after=path.stat()
  if (st.st_size,st.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
   raise RuntimeError("FILE_CHANGED_DURING_HASH")
  print(json.dumps({"sha256":digest,"size":st.st_size,"mtime_ns":st.st_mtime_ns},separators=(",",":")))
if __name__=="__main__":main()
