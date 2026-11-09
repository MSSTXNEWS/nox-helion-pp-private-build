#!/usr/bin/env python3
"""Consolidate the trained NOX 9B adapter into one full-size standalone weight checkpoint."""
import hashlib,json,pathlib,shutil
ROOT=pathlib.Path("/workspace/nox")
BASE=ROOT/"models/NOX_PRIME_9B_INHERITED"
RUN=ROOT/"checkpoints/NOX_PRIME_9B_GENESIS"
FINAL=ROOT/"models/NOX_9B_UNIFIED"
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
 return h.hexdigest()
def main():
 import torch
 from peft import PeftModel
 from transformers import AutoTokenizer
 try:from transformers import Qwen3_5ForConditionalGeneration as Class
 except ImportError:
  from transformers import AutoModelForCausalLM as Class
 receipts=sorted(RUN.glob("pass*/SUCCESS.json"),key=lambda p:int(p.parent.name[4:]))
 if len(receipts)<2:raise RuntimeError("Fewer than two saved training passes. Refusing fake merge.")
 last=receipts[-1].parent
 adapter=last/"adapter"
 weight=adapter/"adapter_model.safetensors"
 if not weight.is_file():raise RuntimeError("Trained NOX adapter not found")
 if FINAL.exists():
  receipt=FINAL/"NOX_UNIFIED_RECEIPT.json"
  if receipt.is_file() and json.loads(receipt.read_text()).get("adapter_sha256")==sha(weight):
   print("NOX_UNIFIED_ALREADY_COMPLETE",flush=True);return
  raise RuntimeError("Different existing unified model; originals preserved")
 if shutil.disk_usage("/workspace").free < 24*1024**3:
  raise RuntimeError("Need 24GiB free for full non-destructive merged 9B checkpoint")
 print("NOX_9B_UNIFICATION_BEGIN",flush=True)
 model=Class.from_pretrained(str(BASE),local_files_only=True,trust_remote_code=False,
      dtype=torch.bfloat16,device_map="cpu",low_cpu_mem_usage=True)
 tuned=PeftModel.from_pretrained(model,str(adapter),is_trainable=False)
 merged=tuned.merge_and_unload(safe_merge=True)
 writing=FINAL.parent/"NOX_9B_UNIFIED_WRITING"
 if writing.exists():raise RuntimeError("Previous incomplete merge exists; do not overwrite it")
 writing.mkdir(parents=True)
 try:
  merged.save_pretrained(str(writing),safe_serialization=True,max_shard_size="4GB")
  AutoTokenizer.from_pretrained(str(BASE),local_files_only=True,trust_remote_code=False).save_pretrained(str(writing))
  shards=sorted(writing.glob("*.safetensors"))
  if len(shards)<2:raise RuntimeError("Full 9B weight shards not saved")
  evidence={"status":"NOX_FULL_9B_MERGED_WEIGHTS_NOT_BENCHMARKED",
    "foundation":"Full Qwen3.5-9B weights inherited and merged with NOX training",
    "original_embryo_lineage":str(ROOT/"embryo/NOX_EMBRYO_TRANSFER_STAGE"),
    "last_training_pass":last.name,"adapter_sha256":sha(weight),
    "shards":[{"file":p.name,"size":p.stat().st_size,"sha256":sha(p)} for p in shards],
    "not_claimed":"independent 9B pretraining, consciousness, or complete transfer of all external skills"}
  (writing/"NOX_UNIFIED_RECEIPT.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
  writing.rename(FINAL)
 except Exception:
  print("MERGE_INCOMPLETE_LOCATION",writing,flush=True)
  raise
 print("NOX_UNIFIED_FULL_WEIGHTS_SAVED",FINAL,flush=True)
if __name__=="__main__":main()
