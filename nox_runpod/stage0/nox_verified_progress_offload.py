#!/usr/bin/env python3
"""NOX no-loss offload: verify a separate mounted backup volume before any cleanup.
Source: shared /workspace/nox. Destination: /workspace-global/NOX_PROGRESS_BACKUP
or Windows mount when truly online. Does not delete checkpoints/models/memory.
"""
import argparse,datetime,hashlib,json,os,pathlib,shutil,sys,time
R=pathlib.Path("/workspace/nox")
SCOPES=("checkpoints","distillation","memory","models","embryo","logs","tools","dispatcher")
CHUNK=8*1024*1024
def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for data in iter(lambda:f.read(CHUNK),b""):h.update(data)
 return h.hexdigest()
def inventory():
 for group in SCOPES:
  d=R/group
  if not d.is_dir():continue
  for root,ds,fs in os.walk(d,followlinks=False):
   ds[:]=[x for x in ds if x not in (".git","__pycache__",".cache","venv","node_modules","site-packages") and not (pathlib.Path(root)/x).is_symlink()]
   for fn in fs:
    p=pathlib.Path(root)/fn
    if p.is_file() and not p.is_symlink() and not fn.endswith((".noxpart",".tmp",".part")):yield p
def backup(dst):
 if not R.is_dir() or not pathlib.Path("/workspace").is_mount():raise RuntimeError("SOURCE_SHARED_DISK_NOT_MOUNTED")
 dst=dst.resolve()
 if not dst.is_dir():raise RuntimeError("BACKUP_MOUNT_MISSING")
 if dst.stat().st_dev==R.stat().st_dev:raise RuntimeError("BACKUP_MUST_BE_SEPARATE_DISK")
 if dst.is_relative_to(R) or R.is_relative_to(dst):raise RuntimeError("BACKUP_PATH_OVERLAP")
 if not any(p.is_mount() for p in (dst,*dst.parents) if str(p)!="/"):
  raise RuntimeError("NO_SEPARATE_MOUNT")
 files=sorted(inventory());ok=copied=changed=failed=0;byte_count=0
 for p in files:
  rel=p.relative_to(R);t=dst/rel
  try:
   before=p.stat()
   if time.time()-before.st_mtime<8:changed+=1;continue
   oldhash=sha(p)
   if (p.stat().st_size,p.stat().st_mtime_ns)!=(before.st_size,before.st_mtime_ns):
    changed+=1;continue
   if t.is_file() and t.stat().st_size==before.st_size and sha(t)==oldhash:
    ok+=1;continue
   if shutil.disk_usage(dst).free<before.st_size+2*1024**3:
    raise RuntimeError("DESTINATION_SPACE_INSUFFICIENT")
   t.parent.mkdir(parents=True,exist_ok=True);tmp=t.with_name(t.name+".noxpart")
   with p.open("rb") as inp,tmp.open("wb") as out:
    shutil.copyfileobj(inp,out,CHUNK);out.flush();os.fsync(out.fileno())
   if sha(tmp)!=oldhash:raise RuntimeError("BACKUP_SHA256_MISMATCH")
   after=p.stat()
   if (after.st_size,after.st_mtime_ns)!=(before.st_size,before.st_mtime_ns) or sha(p)!=oldhash:
    changed+=1;tmp.unlink(missing_ok=True);continue
   os.replace(tmp,t);copied+=1;ok+=1;byte_count+=before.st_size
   print(json.dumps({"event":"VERIFIED","file":str(rel),"bytes":before.st_size}),flush=True)
  except Exception as e:
   failed+=1;print(json.dumps({"event":"BACKUP_ERROR","file":str(rel),"error":str(e)[:200]}),flush=True)
 receipt={"event":"NOX_OFFLOAD_RESULT","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "source":str(R),"destination":str(dst),"files":len(files),"verified":ok,"copied":copied,
  "new_bytes":byte_count,"changed":changed,"failed":failed,
  "complete":ok==len(files) and failed==0 and changed==0,
  "models_and_checkpoints_removed":False}
 target=dst/"NOX_OFFLOAD_RECEIPT.json";temp=target.with_suffix(".tmp")
 with temp.open("w",encoding="utf-8") as f:
  json.dump(receipt,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(temp,target)
 print(json.dumps(receipt,ensure_ascii=False),flush=True)
 if not receipt["complete"]:sys.exit(2)
def main():
 a=argparse.ArgumentParser();a.add_argument("--destination",default="/workspace-global/NOX_PROGRESS_BACKUP")
 v=a.parse_args();backup(pathlib.Path(v.destination))
if __name__=="__main__":main()
