#!/usr/bin/env python3
"""NOX express full-weight save: no fake checkpoints, no partial raw tensor splice.

Can request one safe boundary only when there is recent evidence of completed
optimizer steps. Copies SHA-proven full model to persistent /workspace if space.
Preserves source /opt and never removes historical weights or S03.
"""
import argparse,datetime,fcntl,hashlib,json,os,pathlib,shutil,signal,time
R=pathlib.Path("/workspace/nox");TRAIN=R/"dispatcher/a40_full_parameter"
DIR=pathlib.Path("/opt/nox_full_parameter_A40")
DEST=R/"checkpoints/NOX_EXPRESS_VERIFIED"
STATUS=R/"dispatcher/nox_v3/express_save_status.json"
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for v in iter(lambda:f.read(8*1024*1024),b""):h.update(v)
 return h.hexdigest()
def atomic(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+".tmp")
 with tmp.open("w",encoding="utf-8") as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def read(path):
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError):return {}
def report(status,**kwargs):
 obj={"utc":utc(),"status":status,**kwargs}
 atomic(STATUS,obj);print(json.dumps(obj,ensure_ascii=False),flush=True)
def valid(receipt):
 d=read(receipt)
 if d.get("status")!="FULL_PARAMETER_ADAPTER_FREE_STUDENT_CHECKPOINT_SAVED_NOT_ALL_KNOWLEDGE_ABSORBED":return None
 if not isinstance(d.get("shards"),list) or not d["shards"]:return None
 files=[]
 for shard in d["shards"]:
  name=shard.get("file")
  if not isinstance(name,str) or pathlib.Path(name).name!=name or ".." in name:return None
  p=receipt.parent/name
  if not p.is_file():return None
  expected=shard.get("sha256")
  if not isinstance(expected,str) or len(expected)!=64:return None
  if p.stat().st_size!=int(shard.get("bytes",shard.get("size",0))):return None
  if sha(p)!=expected:return None
  files.append(p)
 return d,files
def active_trainer():
 target="a40_full_parameter_distill_cycle.py"
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdigit():continue
  try:
   argv=[x.decode(errors="replace") for x in (p/"cmdline").read_bytes().split(b"\\0") if x]
   if any(pathlib.Path(a).name==target for a in argv[1:]):return int(p.name)
  except OSError:pass
 return None
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--request-safepoint",action="store_true")
 a=ap.parse_args()
 STATUS.parent.mkdir(parents=True,exist_ok=True)
 with (STATUS.parent/"express_save.lock").open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print("EXPRESS_SAVE_ALREADY_RUNNING");return 2
  p=active_trainer()
  progress=read(TRAIN/"progress.json")
  if a.request_safepoint and p and progress.get("status")=="RUNNING" and int(progress.get("steps_executed_this_cycle") or 0)>=1:
   try:age=time.time()-(TRAIN/"progress.json").stat().st_mtime
   except OSError:age=1e9
   marker=R/"dispatcher/nox_v3/STOP_A40"
   if age<120 and not marker.exists():
    marker.touch()
    report("SAFEPOINT_REQUESTED",trainer_pid=p,steps=progress.get("steps_executed_this_cycle"),
           note="Checkpoint will be saved by trainer at next completed optimizer step; current batch interrupted.")
    # Wait for full-weight serialization and verify, no destructive action.
    for i in range(60):
     if not active_trainer():break
     time.sleep(15)
    # Remove only OUR marker when trainer exited, not user-created markers.
    if not active_trainer() and marker.is_file():marker.unlink()
   elif age>=120:report("HOLD_NO_RECENT_TRAINING_PROGRESS",trainer_pid=p,age_seconds=round(age))
  receipts=sorted(DIR.glob("NOX_FULL_CYCLE_*/NOX_FULL_TRAIN_RECEIPT.json"),key=lambda x:x.stat().st_mtime_ns,reverse=True)
  if not receipts:
   report("HOLD_NO_SAVED_FULL_WEIGHT_CHECKPOINT",active_trainer=active_trainer(),
          training_status=progress.get("status"),steps=progress.get("steps_executed_this_cycle"));return 2
  selected=None
  for rp in receipts:
   v=valid(rp)
   if v:selected=(rp,*v);break
  if not selected:
   report("HOLD_NO_SHA_VERIFIED_CHECKPOINT",receipts_found=len(receipts));return 2
  receipt,data,files=selected
  accepted=float(data.get("after_holdout_loss",1e99))<=float(data.get("baseline_holdout_loss",0))*1.05
  target=DEST/receipt.parent.name
  total=sum(x.stat().st_size for x in files)
  metadata={"source":str(receipt.parent),"cycle":data.get("cycle"),"steps":data.get("steps"),
            "accepted_holdout":accepted,"shards":data["shards"],"source_receipt":str(receipt),
            "checkpoint_quality":"ACCEPTED" if accepted else "CANDIDATE_NOT_PROMOTED"}
  if target.exists() and (target/"NOX_FULL_TRAIN_RECEIPT.json").is_file():
   if all((target/f.name).is_file() and sha(target/f.name)==sha(f) for f in files):
    report("VERIFIED_ALREADY_ON_PERSISTENT_VOLUME",path=str(target),**metadata);return 0
   report("HOLD_EXISTING_TARGET_INCOMPLETE_DO_NOT_OVERWRITE",path=str(target));return 2
  DEST.mkdir(parents=True,exist_ok=True)
  available=shutil.disk_usage(DEST).free
  if available<total+4*1024**3:
   report("HOLD_SHARED_VOLUME_CAPACITY_WINDOWS_DIRECT_SCP_NEEDED",
         bytes_required=total,free_bytes=available,**metadata);return 2
  staged=DEST/("._COPY_"+receipt.parent.name)
  if staged.exists():
   report("HOLD_PREVIOUS_STAGING_EXISTS_NO_OVERWRITE",path=str(staged));return 2
  staged.mkdir()
  for f in files:
   out=staged/f.name
   with f.open("rb") as src,out.open("wb") as dst:
    shutil.copyfileobj(src,dst,8*1024*1024);dst.flush();os.fsync(dst.fileno())
   if sha(out)!=sha(f):
    report("HOLD_COPIED_SHARD_HASH_MISMATCH",file=f.name,stage=str(staged));return 2
  shutil.copy2(receipt,staged/receipt.name)
  # The loading code requires config/tokenizer files to accompany weight shards.
  for f in receipt.parent.iterdir():
   if f.is_file() and f.name not in {x.name for x in files} and f.name!=receipt.name:
    if f.stat().st_size<=50*1024*1024 and f.suffix in (".json",".txt",".model",".tiktoken"):
     shutil.copy2(f,staged/f.name)
  atomic(staged/"NOX_EXPRESS_METADATA.json",metadata)
  os.replace(staged,target)
  report("FULL_WEIGHTS_SHA_VERIFIED_PERSISTENT",path=str(target),bytes=total,**metadata)
  return 0
if __name__=="__main__":raise SystemExit(main())
