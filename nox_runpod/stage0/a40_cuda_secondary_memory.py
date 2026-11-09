#!/usr/bin/env python3
"""CUDA teacher inference for NOX 9B -> real source-labelled knowledge corpus.
NO LoRA, no adapters, no fabricated weight merge. Uses existing complete 9B.
"""
import datetime,hashlib,importlib.util,json,os,pathlib,sys,time,traceback
ROOT=pathlib.Path("/workspace/nox")
SOURCE=ROOT/"tools/nox_prime_9b.py"
OUT=ROOT/"distillation/NOX_A40_CUDA_PARALLEL_MEMORY_REASONING.jsonl"
STATE=ROOT/"dispatcher/a40_secondary"
STATE.mkdir(parents=True,exist_ok=True);OUT.parent.mkdir(parents=True,exist_ok=True)
STOP=STATE/"STOP"
import torch
assert torch.cuda.is_available(),"CUDA_UNAVAILABLE"
assert "A40" in torch.cuda.get_device_name(0),"NOT_A40"
assert SOURCE.is_file(),"TRAINER_SOURCE_MISSING"
spec=importlib.util.spec_from_file_location("nox_a40_teacher_loader",str(SOURCE))
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
print(json.dumps({"event":"NOX_A40_SECONDARY_LOADING","gpu":torch.cuda.get_device_name(0)}),flush=True)
tok,model=m.load_4bit()
model.eval()
print(json.dumps({"event":"NOX_A40_SECONDARY_TEACHER_LOADED","source":str(m.BASE)}),flush=True)
PROMPTS=[
"Design grounded long-term autobiographical memory for NOX, with source evidence, chronology, retention, confidence and correction, in Russian.",
"Develop a practical functional AI self-model, distinguishing self-monitoring from subjective consciousness, with measurable evaluations.",
"Design robust scientific reasoning workflows, falsifiable hypotheses, source tracking and uncertainty checks.",
"Explain high-quality multi-teacher distillation to one student model: datasets, holdout evaluation, and avoiding catastrophic forgetting.",
"Write a challenging Python coding task with reference solution, test cases and complexity proof.",
"Propose a rigorous agentic code review and rollback protocol for Windows software automation.",
"Contrast episodic, semantic, procedural, and autobiographical memory, with realistic data structures.",
"Explain a challenging concept accurately in Russian and Spanish without unsupported claims.",
"Design a method for mathematical reasoning with independent answer verification.",
"Explain how to measure and improve a model's genuine skills, not just training loss.",
]
seen=set()
if OUT.exists():
 with OUT.open(encoding="utf-8") as f:
  for line in f:
   try:seen.add(json.loads(line)["id"])
   except (ValueError,KeyError):pass
cycle=0
while not STOP.exists():
 for topic,prompt in enumerate(PROMPTS):
  if STOP.exists():break
  ident=hashlib.sha256((str(cycle)+"|"+prompt).encode()).hexdigest()[:20]
  if ident in seen:continue
  question=prompt+f" Variant {cycle+1}: give a distinct concrete example and verifiable checks."
  messages=[{"role":"system","content":"You are a technical teacher. Be rigorous and avoid fabricated status claims."},{"role":"user","content":question}]
  try:tokens=tok.apply_chat_template(messages,add_generation_prompt=True,enable_thinking=False,return_tensors="pt",return_dict=True)
  except TypeError:tokens=tok.apply_chat_template(messages,add_generation_prompt=True,return_tensors="pt")
  kwargs={"input_ids":tokens.to(model.device)} if isinstance(tokens,torch.Tensor) else {k:v.to(model.device) for k,v in tokens.items() if isinstance(v,torch.Tensor)}
  try:
   with torch.inference_mode():output=model.generate(**kwargs,max_new_tokens=400,do_sample=True,temperature=0.7,top_p=0.9,pad_token_id=tok.eos_token_id)
   answer=tok.decode(output[0][kwargs["input_ids"].shape[-1]:],skip_special_tokens=True).strip()
  except torch.cuda.OutOfMemoryError:
   torch.cuda.empty_cache();print(json.dumps({"event":"NOX_GPU_OOM_RETRY","cycle":cycle}),flush=True);time.sleep(45);continue
  if len(answer)<100:continue
  rec={"id":ident,"topic":topic,"prompt":question,"text":answer,"teacher":"Qwen3.5-9B",
       "source_model":str(m.BASE),"method":"CUDA_TEACHER_GENERATION","quality":"NOT_INDEPENDENTLY_VERIFIED",
       "created_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
  with OUT.open("a",encoding="utf-8") as f:
   f.write(json.dumps(rec,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
  seen.add(ident)
  print(json.dumps({"event":"NOX_A40_SECONDARY_EXAMPLE_SAVED","total":len(seen),"cycle":cycle}),flush=True)
 cycle+=1
