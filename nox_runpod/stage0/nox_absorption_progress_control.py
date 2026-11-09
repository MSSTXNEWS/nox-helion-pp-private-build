#!/usr/bin/env python3
"""NOX source-of-truth progress supervisor. CPU only; no weight mutations.
Stage completion counts: 3 distinct teacher sources, durable knowledge, full-
parameter student optimizer steps, hash-verified full checkpoints and Windows backup.
'Full teacher absorption' is NEVER a percent because no valid denominator exists.
"""
import argparse,datetime,fcntl,hashlib,json,os,pathlib,sqlite3,subprocess,time
R=pathlib.Path("/workspace/nox")
C=R/"dispatcher/absorption_control"
S03=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
THREE=R/"dispatcher/a40_unification/status.json"
FULL=R/"dispatcher/a40_full_parameter/progress.json"
TEACHERS=("Qwen3.5-9B","Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B")
C.mkdir(parents=True,exist_ok=True)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atom(p,d):
 t=p.with_suffix(".tmp")
 with t.open("w",encoding="utf8") as f:
  json.dump(d,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def read(p):
 try:return json.loads(p.read_text(encoding="utf8-sig")) if p.is_file() else {}
 except Exception:return {}
def gpu():
 try:
  s=subprocess.check_output(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.free,memory.total,temperature.gpu",
   "--format=csv,noheader,nounits"],timeout=10,text=True).splitlines()[0]
  a=[x.strip() for x in s.split(",")]
  return {"name":a[0],"compute_percent":int(a[1]),"vram_used_mib":int(a[2]),
   "vram_free_mib":int(a[3]),"vram_total_mib":int(a[4]),"temperature_c":int(a[5])}
 except Exception as e:return {"error":str(e)[:150]}
def counts():
 data={t:0 for t in TEACHERS}
 if not S03.exists():return data,"S03_NOT_FOUND"
 try:
  c=sqlite3.connect("file:"+str(S03)+"?mode=ro",uri=True,timeout=5)
  try:
   for teacher,count in c.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher"):
    if teacher in data:data[teacher]=count
  finally:c.close()
  return data,"S03_OK"
 except Exception as e:return data,"S03_ERROR_"+str(e)[:80]
def active():
 labels={"a5000_pure_distillation.py":"teacher_9b_A5000",
   "a5000_cuda_secondary_direct.py":"teacher_9b_A5000_secondary",
   "a40_cuda_distillation_direct.py":"teacher_9b_A40",
   "a40_full_parameter_distill_cycle.py":"full_student_optimizer_A40",
   "a40_3teacher_unified_corpus.py":"three_teacher_curator_A40",
   "a40_unified_nox_s03_memory.py":"S03_memory_A40"}
 found=[]
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdecimal():continue
  try:
   parts=(p/"cmdline").read_bytes().split(b"\x00")
   if not parts or not (b"python" in parts[0].lower() or b"python" in parts[0].lower()):continue
   cmd=" ".join(x.decode("utf8","replace") for x in parts[1:])
   for term,label in labels.items():
    if term in cmd:found.append({"pid":int(p.name),"role":label})
  except (OSError,PermissionError):pass
 return found
def backup():
 out={}
 for node in ("A5000","A40"):
  p=R/"dispatcher"/("windows_verified_"+node+".json")
  j=read(p)
  out[node]={"receipt_present":bool(j),"claimed_status":j.get("status"),
    "verified_files_claimed":j.get("verified_file_count"),
    "verified_at":j.get("verified_at"),
    "verification":"RECEIPT_REPORTED_BY_WINDOWS_NOT_AN_INDEPENDENT_RECHECK"}
 return out
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
 return h.hexdigest()
def fullproof():
 # A40 only: a 100% status is NOT trusted until all full-weight shard hashes match.
 prog=read(FULL)
 result={"status":"NOT_VERIFIED","accepted_full_checkpoints":0,"cycle_percent":None}
 if prog.get("status")!="COMPLETE_VERIFIED":return result
 dest=pathlib.Path(str(prog.get("extra",{}).get("output","")))
 if not dest.is_dir() or not str(dest).startswith("/opt/nox_full_parameter_A40/"):
  result["status"]="CHECKPOINT_OUTPUT_MISSING";return result
 receipt=read(dest/"NOX_FULL_TRAIN_RECEIPT.json")
 if receipt.get("no_adapter_training") is not True or receipt.get("steps",0)<1:
  result["status"]="CHECKPOINT_NOT_ACCEPTABLE";return result
 shards=receipt.get("shards",[])
 if len(shards)<2 or sum(int(x.get("bytes",0)) for x in shards)<14*1024**3:
  result["status"]="CHECKPOINT_TOO_SMALL";return result
 # Cache hash verification for unchanged receipt, do not re-hash huge shards every minute.
 cached=read(C/"verified_full_checkpoint.json")
 checksum=sha(dest/"NOX_FULL_TRAIN_RECEIPT.json")
 if cached.get("receipt_sha256")==checksum and cached.get("status")=="FULL_WEIGHTS_SHA256_VERIFIED":
  return {"status":"FULL_WEIGHTS_SHA256_VERIFIED","accepted_full_checkpoints":1,"cycle_percent":100}
 for entry in shards:
  f=dest/entry.get("file","")
  if not f.is_file() or f.stat().st_size!=entry.get("bytes") or sha(f)!=entry.get("sha256"):
   result["status"]="CHECKPOINT_SHARD_HASH_FAILED";return result
 atom(C/"verified_full_checkpoint.json",{"status":"FULL_WEIGHTS_SHA256_VERIFIED","receipt_sha256":checksum,
  "output":str(dest),"utc":utc()})
 return {"status":"FULL_WEIGHTS_SHA256_VERIFIED","accepted_full_checkpoints":1,"cycle_percent":100}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--node",choices=("A5000","A40"),required=True);ap.add_argument("--once",action="store_true")
 a=ap.parse_args()
 lk=(C/(a.node+".lock")).open("a+")
 try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print("NOX_PROGRESS_ALREADY_RUNNING",a.node,flush=True);return
 while not (C/("STOP_"+a.node)).exists():
  t,s03=counts();unify=read(THREE);f=read(FULL)
  ready=sum(v>=8 for v in t.values())
  # Data-source coverage is a defined finite 0-100 task, NOT neural absorption.
  cover=round(100*ready/3,2)
  proof=fullproof() if a.node=="A40" else {"status":"CHECK_ON_A40","accepted_full_checkpoints":None,"cycle_percent":None}
  cycle_status=f.get("status","NOT_STARTED")
  stage=(float(f.get("cycle_progress_percent")) if cycle_status=="RUNNING" and isinstance(f.get("cycle_progress_percent"),(int,float)) else proof.get("cycle_percent"))
  doc={"utc":utc(),"node":a.node,"status":"MONITORING","gpu":gpu(),
   "teacher_data_rows":t,"s03_status":s03,
   "teacher_sources_with_at_least_8_items":ready,"source_coverage_percent":cover,
   "unification_status":unify.get("status","NOT_READY"),
   "active_processes":active(),"full_weight_optimizer_status":cycle_status,
   "full_weight_optimizer_steps":f.get("steps_executed_this_cycle",0),
   "full_weight_optimizer_target_steps":f.get("target_steps_this_cycle",0),
   "verifiable_one_cycle_progress_percent":stage,
   "full_weight_checkpoint_proof":proof,"windows_backup_receipts":backup(),
   "full_teacher_knowledge_absorption_percent":None,
   "adapters_permitted":False,
   "note":"Source coverage is not model training; 100% full-weight cycle requires standalone SHA-verified checkpoint"}
  atom(C/(a.node+"_status.json"),doc)
  print(json.dumps({"node":a.node,"gpu":doc["gpu"],"coverage_pct":cover,
   "counts":t,"weights_cycle":cycle_status,"full_proof":proof["status"]},ensure_ascii=False),flush=True)
  if a.once:break
  for _ in range(60):
   if (C/("STOP_"+a.node)).exists():break
   time.sleep(1)
if __name__=="__main__":main()
