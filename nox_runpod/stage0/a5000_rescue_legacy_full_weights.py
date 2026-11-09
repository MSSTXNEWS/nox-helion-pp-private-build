#!/usr/bin/env python3
"""A5000 ONLY: rescue historical adapter-trained NOX deltas into self-contained full weights.
This is a one-time historical consolidation, NOT new adapter training, NOT fresh distillation.
No deletion, no modifications to active checkpoint or model originals.
"""
import datetime,hashlib,json,os,pathlib,shutil,sys
R=pathlib.Path("/workspace/nox")
OUT=pathlib.Path("/opt/nox_historical_full_weights")
WORK=R/"dispatcher/a5000_legacy_full_weight_rescue"
WORK.mkdir(parents=True,exist_ok=True)
ITEMS=[
 ("knowledge","NOX_9B_KNOWLEDGE","NOX_9B_UNIFIED"),
 ("genesis","NOX_PRIME_9B_GENESIS","NOX_PRIME_9B_INHERITED"),
 ("parallel","NOX_9B_PARALLEL_TECH","NOX_PRIME_9B_INHERITED"),
 ("background","NOX_A5000_BACKGROUND_KNOWLEDGE","NOX_9B_UNIFIED"),
]
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
 return h.hexdigest()
def note(msg,**kw):
 row={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"event":msg,**kw}
 print(json.dumps(row,ensure_ascii=False),flush=True)
 with (WORK/"rescue.log.jsonl").open("a",encoding="utf8") as f:f.write(json.dumps(row,ensure_ascii=False)+"\n")
def memory_avail():
 for x in pathlib.Path("/proc/meminfo").read_text().splitlines():
  if x.startswith("MemAvailable:"):return int(x.split()[1])*1024
 return 0
def candidates():
 for name,dir_name,base_name in ITEMS:
  d=R/"checkpoints"/dir_name
  passes=[]
  for r in d.glob("pass*/SUCCESS.json"):
   try:
    n=int(r.parent.name[4:])
    w=r.parent/"adapter/adapter_model.safetensors"
    config=r.parent/"adapter/adapter_config.json"
    if w.is_file() and config.is_file():
     receipt=json.loads(r.read_text())
     if receipt.get("adapter_sha256") and sha(w)!=receipt["adapter_sha256"]:continue
     passes.append((n,r,w))
   except (ValueError,OSError,KeyError):continue
  if not passes:continue
  number,receipt,weights=max(passes)
  base=R/"models"/base_name
  if not (base/"config.json").exists() or not list(base.glob("*.safetensors")):
   note("HOLD_BASE_MISSING",source=name,base=str(base));continue
  yield name,base,weights,number
def convert(name,base,weights,number):
 import torch
 from peft import PeftModel
 from transformers import AutoTokenizer
 try:from transformers import Qwen3_5ForConditionalGeneration as Class
 except ImportError:
  from transformers import AutoModelForCausalLM as Class
 dest=OUT/("NOX_FULL_"+name.upper()+"_PASS"+str(number))
 fullreceipt=dest/"NOX_FULL_WEIGHTS_RECEIPT.json"
 if dest.exists():
  if not fullreceipt.exists():raise RuntimeError("UNVERIFIED_OUTPUT_ALREADY_EXISTS: "+str(dest))
  info=json.loads(fullreceipt.read_text())
  if info.get("historical_delta_sha256")!=sha(weights):raise RuntimeError("OUTPUT_HISTORY_MISMATCH")
  for shard in info["shards"]:
   p=dest/shard["file"]
   if not p.is_file() or p.stat().st_size!=shard["bytes"] or sha(p)!=shard["sha256"]:
    raise RuntimeError("EXISTING_FULL_OUTPUT_FAILED_SHA")
  note("FULL_WEIGHTS_ALREADY_VERIFIED",lineage=name,path=str(dest));return
 # Strong non-destructive resource gates: avoid OOM and data loss.
 required_disk=24*1024**3
 if shutil.disk_usage(OUT).free<required_disk:raise RuntimeError("HOLD_DISK_LT_24GIB")
 if memory_avail()<36*1024**3:raise RuntimeError("HOLD_CPU_RAM_LT_36GIB")
 stage=OUT/("._WRITING_"+name)
 if stage.exists():raise RuntimeError("HOLD_PREVIOUS_STAGING_NOT_DELETED")
 stage.mkdir()
 note("HISTORICAL_CONSOLIDATION_BEGIN",lineage=name,base=str(base),pass_number=number)
 try:
  model=Class.from_pretrained(str(base),local_files_only=True,trust_remote_code=False,
    dtype=torch.bfloat16,device_map="cpu",low_cpu_mem_usage=True)
  adapter=PeftModel.from_pretrained(model,str(weights.parent),is_trainable=False)
  merged=adapter.merge_and_unload(safe_merge=True)
  merged.save_pretrained(str(stage),safe_serialization=True,max_shard_size="4GB")
  AutoTokenizer.from_pretrained(str(base),local_files_only=True,trust_remote_code=False).save_pretrained(str(stage))
  shards=list(sorted(stage.glob("*.safetensors")))
  if sum(x.stat().st_size for x in shards)<13*1024**3:raise RuntimeError("INCOMPLETE_FULL_WEIGHTS")
  rec={"status":"HISTORICAL_LORA_DELTA_MERGED_TO_FULL_WEIGHTS_NOT_NEW_DISTILLATION",
       "lineage":name,"base":str(base),"pass":number,"historical_delta_sha256":sha(weights),
       "shards":[{"file":x.name,"bytes":x.stat().st_size,"sha256":sha(x)} for x in shards],
       "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "destination_is_ephemeral":True,"legacy_originals_preserved":True}
  (stage/"NOX_FULL_WEIGHTS_RECEIPT.json").write_text(json.dumps(rec,indent=2,ensure_ascii=False))
  os.rename(stage,dest)
  note("HISTORICAL_FULL_WEIGHTS_VERIFIED_SAVED",lineage=name,path=str(dest))
 finally:
  pass
def main():
 import fcntl
 if "A5000" not in __import__("subprocess").check_output(["nvidia-smi","--query-gpu=name","--format=csv,noheader"],text=True):raise RuntimeError("WRONG_POD_NOT_A5000")
 OUT.mkdir(parents=True,exist_ok=True)
 if OUT.stat().st_dev==R.stat().st_dev:raise RuntimeError("OUTPUT_NOT_ON_SEPARATE_CONTAINER_DISK")
 lock=(WORK/"rescue.lock").open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  note("ALREADY_RUNNING");return
 for name,base,weights,num in candidates():
  try:convert(name,base,weights,num)
  except Exception as e:note("CONSOLIDATION_HOLD",lineage=name,reason=str(e)[:260])
 note("RESCUE_SCAN_COMPLETE",no_source_deletion=True)
if __name__=="__main__":main()
