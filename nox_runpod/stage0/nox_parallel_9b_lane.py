#!/usr/bin/env python3
"""NOX auxiliary 9B QLoRA lane on A5000.
Separate corpus/checkpoints from main lane. Never mutates donor/other adapter.
"""
import importlib.util,json,pathlib,sys,torch,os,time,datetime,hashlib
R=pathlib.Path("/workspace/nox")
SOURCE=R/"tools/nox_prime_9b_parallel_base.py"
if not SOURCE.is_file():raise RuntimeError("Primary trainer source not ready")
if not torch.cuda.is_available():raise RuntimeError("CUDA GPU unavailable")
# Be conservative: primary learner takes priority; avoid exhausting 24GB.
mem=torch.cuda.mem_get_info()[0]
if mem < 9*1024**3:raise RuntimeError("NOX_PARALLEL_HOLD: less than 9GiB GPU free")
spec=importlib.util.spec_from_file_location("nox_secondary_lane",str(SOURCE))
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
m.WORK=R/"checkpoints/NOX_9B_PARALLEL_TECH"
m.CORPUS=R/"distillation/NOX_9B_PARALLEL_TECH.jsonl"
m.TOPICS=[
 "Advanced code generation and secure Python programming",
 "Distributed systems fault diagnosis and recovery",
 "CUDA performance profiling and memory optimization",
 "Mathematical reasoning and proofs",
 "Scientific experimentation and hypothesis testing",
 "Version control and software architecture",
 "Russian Spanish translation and cross-lingual learning",
 "Software testing and automated code improvement",
 "Knowledge provenance and retrieval augmented generation",
 "GPU efficient training and gradient methods",
 "Long-term autobiographical memory design",
 "SQL performance and consistency"]
m.verify()
m.WORK.mkdir(parents=True,exist_ok=True)
log=m.WORK/"parallel_progress.jsonl"
started=time.monotonic()
max_seconds=12*3600
best=float("inf")
stagnant=0
# Keep existing saved passes; never replay the same pass.
completed=sorted(m.WORK.glob("pass*/SUCCESS.json"),key=lambda p:int(p.parent.name[4:]))
pass_num=int(completed[-1].parent.name[4:]) if completed else 0
if completed:
 for path in completed:
  try:best=min(best,float(json.loads(path.read_text())["mean_training_loss"]))
  except (ValueError,KeyError):pass
tok,model=m.load_4bit()
# Corpus generation uses real teacher weights. Generated examples are not independently fact-checked.
m.create_corpus(tok,model,8)
del model
torch.cuda.empty_cache()
while time.monotonic()-started < max_seconds and stagnant < 3:
 if (m.WORK/"STOP_AFTER_CURRENT_PASS").exists():
  print("NOX_PARALLEL_STOP_REQUESTED",flush=True)
  break
 primary_passes=len(list((R/"checkpoints/NOX_PRIME_9B_GENESIS").glob("pass*/SUCCESS.json")))
 # Avoid continuing on a runaway GPU bill after primary training and stage2 end.
 record={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "event":"NOX_PARALLEL_PRIMARY_PROGRESS_SNAPSHOT","primary_passes_saved":primary_passes,
         "secondary_passes_saved":pass_num}
 with log.open("a",encoding="utf-8") as out:out.write(json.dumps(record)+"\\n")
 tok,model=m.load_4bit()
 # One new pass, preserving the prior adapter. Use auto-OOM downshift built into the pinned trainer.
 m.train(tok,model,pass_num+1,768,4,16,batch_size=2)
 del model
 torch.cuda.empty_cache()
 pass_num+=1
 receipt=m.WORK/f"pass{pass_num}"/"SUCCESS.json"
 if not receipt.is_file():raise RuntimeError("No independently saved pass checkpoint")
 value=float(json.loads(receipt.read_text())["mean_training_loss"])
 if value<best-0.001:best=value;stagnant=0
 else:stagnant+=1
 print(json.dumps({"event":"NOX_PARALLEL_SAVED","pass_number":pass_num,
   "mean_training_loss":value,"primary_saved_passes":primary_passes,
   "no_improvement_passes":stagnant}),flush=True)
result={"status":"PARALLEL_9B_ADAPTERS_SAVED_NOT_MERGED",
        "passes":pass_num,"training_loss_best":best,
        "location":str(m.WORK),"no_improvement_passes":stagnant,
        "must_not_merge_blindly":True}
(m.WORK/"parallel_result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result),flush=True)
