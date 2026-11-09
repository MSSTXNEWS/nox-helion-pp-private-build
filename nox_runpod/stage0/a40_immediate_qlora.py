#!/usr/bin/env python3
"""Start isolated NOX 9B QLoRA on A40 using existing PyTorch environment.
No nvcc, llama.cpp, model downloads or writes to A5000's checkpoints.
"""
import json,os,pathlib,sys,importlib.util,time,traceback
ROOT=pathlib.Path("/workspace/nox")
TOOLS=ROOT/"tools"
TRAINER=TOOLS/"nox_prime_9b.py"
BASE=ROOT/"models/NOX_9B_UNIFIED"
CORPUS=ROOT/"distillation/nox_9b_knowledge_stage2.jsonl"
WORK=ROOT/"checkpoints/NOX_A40_INDEPENDENT_ADAPTER"
WORK.mkdir(parents=True,exist_ok=True)
if not (BASE/"NOX_UNIFIED_RECEIPT.json").is_file():raise RuntimeError("HOLD: no verified NOX 9B base")
if not TRAINER.is_file():raise RuntimeError("HOLD: no trained 9B Python trainer")
if not CORPUS.is_file():raise RuntimeError("HOLD: stage2 knowledge corpus missing")
import torch
if not torch.cuda.is_available():raise RuntimeError("HOLD: A40 PyTorch CUDA not accessible")
print(json.dumps({"event":"NOX_A40_GPU_CONFIRMED","name":torch.cuda.get_device_name(0),"vram":torch.cuda.get_device_properties(0).total_memory}),flush=True)
records=[]
with CORPUS.open(encoding="utf-8") as f:
 for line in f:
  try:
   r=json.loads(line)
   if len(str(r.get("text","")))>80:records.append(r)
  except (ValueError,TypeError):pass
if len(records)<48:raise RuntimeError("HOLD: fewer than 48 real knowledge records")
# Immutable snapshot for independent A40 training. No modification of source files.
snap=WORK/"input_snapshot.jsonl"
if not snap.exists():
 with snap.open("x",encoding="utf-8") as out:
  for r in records:out.write(json.dumps(r,ensure_ascii=False)+"\n")
  out.flush();os.fsync(out.fileno())
spec=importlib.util.spec_from_file_location("nox_a40_single_training",str(TRAINER))
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
m.BASE=BASE;m.CORPUS=snap;m.WORK=WORK
print(json.dumps({"event":"NOX_A40_INDEPENDENT_QLORA_BEGIN","input_examples":len(records),"checkpoint_dir":str(WORK)}),flush=True)
tok,model=m.load_4bit()
try:
 m.train(tok,model,1,512,4,16,batch_size=1)
finally:
 del model
 torch.cuda.empty_cache()
receipt=WORK/"pass1/SUCCESS.json"
if not receipt.is_file():raise RuntimeError("NOX_A40_QLORA_NO_CHECKPOINT")
print(json.dumps({"event":"NOX_A40_GPU_TRAINING_SAVED","receipt":str(receipt)}),flush=True)
