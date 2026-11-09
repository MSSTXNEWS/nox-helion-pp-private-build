#!/usr/bin/env python3
"""NOX stage 2: continual knowledge training of the independently saved UNIFIED NOX 9B model.
Generates new multilingual exercises, runs 3 passes, saves merged standalone weights.
Not a claim of independent pretraining, consciousness, or verified full teacher knowledge.
"""
import hashlib,importlib.util,json,pathlib,sys
ROOT=pathlib.Path("/workspace/nox")
BASE=ROOT/"models/NOX_9B_UNIFIED"
WORK=ROOT/"checkpoints/NOX_9B_KNOWLEDGE"
CORPUS=ROOT/"distillation/nox_9b_knowledge_stage2.jsonl"
FINAL=ROOT/"models/NOX_9B_KNOWLEDGE_UNIFIED"
TOOLS=ROOT/"tools"
def import_file(path,name):
 spec=importlib.util.spec_from_file_location(name,str(path))
 if spec is None or spec.loader is None:raise RuntimeError("Cannot import "+str(path))
 mod=importlib.util.module_from_spec(spec)
 sys.modules[name]=mod
 spec.loader.exec_module(mod)
 return mod
def verify():
 receipt=BASE/"NOX_UNIFIED_RECEIPT.json"
 if not receipt.is_file():raise RuntimeError("Stage 1 unified 9B checkpoint NOT ready")
 info=json.loads(receipt.read_text(encoding="utf-8"))
 if info.get("status")!="NOX_FULL_9B_MERGED_WEIGHTS_NOT_BENCHMARKED":
  raise RuntimeError("Stage 1 receipt invalid")
 for item in info.get("shards",[]):
  p=BASE/item["file"]
  if not p.is_file() or p.stat().st_size!=item["size"]:
   raise RuntimeError("Unified weight shard missing "+str(p))
  h=hashlib.sha256()
  with p.open("rb") as f:
   for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
  if h.hexdigest()!=item["sha256"]:raise RuntimeError("Unified weight SHA mismatch "+str(p))
 if not (BASE/"config.json").exists():raise RuntimeError("Stage 1 unified model config absent")
 print("NOX_STAGE2_STANDALONE_FULL_9B_VERIFIED",flush=True)
def main():
 verify()
 trainer=import_file(TOOLS/"nox_prime_9b.py","nox_prime_9b_stage2")
 trainer.BASE=BASE
 trainer.WORK=WORK
 trainer.CORPUS=CORPUS
 trainer.TOPICS+=["Knowledge synthesis across disciplines","Proof checking and critical thinking",
                 "Computer networking diagnostics","Research design and experimental controls",
                 "Unit testing and property testing","Spanish to Russian technical translation",
                 "Formal logic and fallacies","Reliability engineering and incident response"]
 tok,model=trainer.load_4bit()
 trainer.create_corpus(tok,model,12)
 del model
 import torch
 torch.cuda.empty_cache()
 tok,model=trainer.load_4bit()
 trainer.train(tok,model,3,512,4,32)
 del model
 torch.cuda.empty_cache()
 merger=import_file(TOOLS/"nox_9b_merge.py","nox_merge_knowledge_stage2")
 merger.BASE=BASE
 merger.RUN=WORK
 merger.FINAL=FINAL
 merger.main()
 receipt=FINAL/"NOX_UNIFIED_RECEIPT.json"
 if not receipt.is_file():raise RuntimeError("Stage 2 full model not saved")
 print("NOX_STAGE2_KNOWLEDGE_TRAINING_AND_MERGED_9B_COMPLETE",flush=True)
if __name__=="__main__":
 main()
