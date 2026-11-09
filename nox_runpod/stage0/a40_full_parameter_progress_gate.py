#!/usr/bin/env python3
"""NOX A40 full-parameter distillation gate and measurable progress, without adapters.

The process tests CUDA/CPU/disk/model/dataset and sets a truthful HOLD if all-parameter
9B training cannot be provisioned safely. Never silently switches to LoRA/QLoRA.
On an externally verified full-weight training receipt, it can advance progress
through validation stages. Progress to 100% is for ONE defined training cycle,
not a claim of all knowledge transferred or consciousness.
"""
import argparse,datetime,fcntl,hashlib,json,os,pathlib,shutil,subprocess,sys,time
R=pathlib.Path("/workspace/nox")
D=R/"dispatcher/a40_full_parameter"
D.mkdir(parents=True,exist_ok=True)
MODEL=R/"models/NOX_9B_UNIFIED"
INPUT=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
STAGE=R/"checkpoints/NOX_A40_FULL_PARAMETER"
STAGE.mkdir(parents=True,exist_ok=True)
STATE=D/"progress.json"
TARGET_STEPS=int(os.environ.get("NOX_TARGET_STEPS","100"))
if TARGET_STEPS<1 or TARGET_STEPS>100000:raise ValueError("invalid target steps")
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(path,data):
 tmp=path.with_suffix(".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def state(status,stage,completed=0,verified=0,error="",details=None):
 # Only real optimizer steps accompanied by verified receipts count as completed.
 pct=round(100*min(completed,TARGET_STEPS)/TARGET_STEPS,2)
 doc={"utc":stamp(),"status":status,"stage":stage,"target_optimizer_steps":TARGET_STEPS,
      "completed_verified_steps":completed,"training_step_progress_percent":pct,
      "overall_cycle_progress_percent":100 if status=="COMPLETE_VERIFIED" else None,
      "all_teacher_knowledge_absorbed_percent":None,
      "neural_full_weight_checkpoints_verified":verified,
      "teacher_dataset_present":INPUT.is_file(),
      "base_full_weights_present":(MODEL/"NOX_UNIFIED_RECEIPT.json").is_file(),
      "adapters_allowed":False,"adapter_free_full_parameter_training_only":True,
      "error":error,"details":details or {}}
 atomic(STATE,doc);print(json.dumps(doc,ensure_ascii=False),flush=True)
 return doc
def cuda():
 o=subprocess.run(["nvidia-smi","--query-gpu=name,memory.total,memory.free,temperature.gpu",
                    "--format=csv,noheader,nounits"],text=True,capture_output=True,check=True,timeout=15).stdout.splitlines()[0]
 s=[x.strip() for x in o.split(",")]
 return {"gpu":s[0],"vram_total_mib":int(s[1]),"vram_free_mib":int(s[2]),"temp_c":int(s[3])}
def ram():
 with open("/proc/meminfo") as f:
  data={}
  for line in f:
   parts=line.split()
   if len(parts)>1 and parts[0] in ("MemAvailable:","MemTotal:"):data[parts[0][:-1]]=int(parts[1])//1024
 return data
def dataset_count():
 import sqlite3
 if not INPUT.is_file():return 0
 c=sqlite3.connect("file:"+str(INPUT)+"?mode=ro",uri=True,timeout=5)
 try:return c.execute("SELECT COUNT(*) FROM knowledge WHERE teacher != 'UNATTRIBUTED'").fetchone()[0]
 finally:c.close()
def previous():
 p=STAGE/"TRAINING_STEPS.jsonl";done=set()
 if not p.exists():return 0
 with p.open() as f:
  for line in f:
   try:
    rec=json.loads(line)
    if rec["status"]=="FULL_WEIGHT_OPTIMIZER_STEP_VERIFIED" and rec["student_full_checkpoint_sha256"]:
     done.add(int(rec["step"]))
   except (ValueError,KeyError):pass
 return len(done)
def preflight():
 gpu=cuda();mem=ram();free=shutil.disk_usage("/workspace").free//(1024**3)
 base=MODEL/"NOX_UNIFIED_RECEIPT.json"
 if "A40" not in gpu["gpu"]:return "NOT_A40",gpu,mem,free
 if not base.is_file():return "STANDALONE_9B_BASE_NOT_VERIFIED",gpu,mem,free
 if dataset_count()<48:return "LESS_THAN_48_ATTRIBUTED_S03_EXAMPLES",gpu,mem,free
 if free<23:return "NEED_23_GIB_PERSISTENT_DISK_FOR_FULL_CHECKPOINT",gpu,mem,free
 if gpu["temp_c"]>=75:return "GPU_TEMP_HOLD",gpu,mem,free
 if gpu["vram_free_mib"]<18000:return "NEED_18_GIB_FREE_VRAM_FOR_FULL_WEIGHT_SETUP",gpu,mem,free
 # No native all-parameter 9B checkpointed optimizer is installed here.
 # Refuse pretending that a PEFT/4-bit inference job would count as training.
 return "FULL_9B_ALL_PARAMETER_OPTIMIZER_NOT_INSTALLED",gpu,mem,free
def main():
 lock=(D/"preflight.lock").open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  print("NOX_FULL_TRAINER_PREFLIGHT_ALREADY_RUNNING",flush=True);return
 verified=previous()
 try:
  reason,gpu,mem,free=preflight()
  state("HOLD","FULL_PARAMETER_TRAINING_PREFLIGHT",completed=verified,verified=0,
        error=reason,details={"gpu":gpu,"ram_mib":mem,"persistent_disk_free_gib":free,
        "attributed_s03_rows":dataset_count(),"required_next":"Implement and run true optimizer, then hash-check durable whole-model checkpoint"})
 except Exception as exc:
  state("ERROR","PREFLIGHT",completed=verified,error=str(exc)[:300])
if __name__=="__main__":main()
