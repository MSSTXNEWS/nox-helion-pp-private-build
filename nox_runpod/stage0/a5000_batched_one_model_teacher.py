#!/usr/bin/env python3
"""A5000 single-model batched CUDA teacher extraction.
Only source-labelled training examples. No adapters / no optimizer / no weight updates.
Maintains the SAME stable IDs and JSONL file as previous single-example worker.
"""
import datetime,hashlib,importlib.util,json,os,pathlib,sys,time
import torch
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/a5000_pure_distillation"
OUT=R/"distillation/NOX_A5000_PURE_DISTILLATION.jsonl"
SOURCE=R/"tools/nox_prime_9b.py"
S.mkdir(parents=True,exist_ok=True);OUT.parent.mkdir(parents=True,exist_ok=True)
assert torch.cuda.is_available() and "A5000" in torch.cuda.get_device_name(0),"HOLD_NOT_A5000_CUDA"
assert SOURCE.is_file(),"HOLD_TRAINER_MODEL_LOADER_MISSING"
spec=importlib.util.spec_from_file_location("nox_batched_teacher",str(SOURCE))
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
torch.backends.cuda.matmul.allow_tf32=True
tok,model=mod.load_4bit()
model.eval()
# Correct left-padding for variable-length causal generation prompts.
tok.padding_side="left"
if tok.pad_token_id is None:tok.pad_token=tok.eos_token
print(json.dumps({"event":"NOX_A5000_BATCHED_TEACHER_LOADED","gpu":torch.cuda.get_device_name(0),"source":str(mod.BASE)}),flush=True)
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
"Explain how to measure and improve a model's genuine skills, not just training loss."
]
def load_seen():
 result=set()
 if OUT.exists():
  with OUT.open("r",encoding="utf-8") as f:
   for line in f:
    try:
     row=json.loads(line)
     if row.get("id"):result.add(row["id"])
    except (ValueError,TypeError):pass
 return result
seen=load_seen()
max_batch=int(os.environ.get("NOX_A5000_MAX_BATCH","4"))
max_batch=max(1,min(4,max_batch))
cycle=0
while not (S/"STOP").exists():
 tasks=[]
 for topic,prompt in enumerate(PROMPTS):
  ident=hashlib.sha256((str(cycle)+"|"+prompt).encode()).hexdigest()[:20]
  if ident in seen:continue
  question=prompt+f" Variant {cycle+1}: give a distinct concrete example and verifiable checks."
  tasks.append((ident,topic,question))
 for i in range(0,len(tasks),max_batch):
  if (S/"STOP").exists():break
  batch=tasks[i:i+max_batch]
  pos=0
  while pos<len(batch) and not (S/"STOP").exists():
   batch_size=min(max_batch,len(batch)-pos)
   subset=batch[pos:pos+batch_size]
   prompts=[]
   for _,_,question in subset:
    msgs=[{"role":"system","content":"You are a technical teacher. Be rigorous and avoid fabricated status claims."},
          {"role":"user","content":question}]
    try:
     p=tok.apply_chat_template(msgs,add_generation_prompt=True,enable_thinking=False,tokenize=False)
    except TypeError:
     p=tok.apply_chat_template(msgs,add_generation_prompt=True,tokenize=False)
    prompts.append(p)
   encoded=tok(prompts,return_tensors="pt",padding=True,truncation=True,max_length=768)
   encoded={k:v.to(model.device) for k,v in encoded.items()}
   try:
    with torch.inference_mode():
     output=model.generate(**encoded,max_new_tokens=300,do_sample=True,temperature=0.7,
       top_p=0.9,pad_token_id=tok.pad_token_id)
    responses=[tok.decode(output[j][encoded["input_ids"].shape[-1]:],skip_special_tokens=True).strip()
        for j in range(len(subset))]
   except torch.cuda.OutOfMemoryError:
    del encoded
    torch.cuda.empty_cache()
    if batch_size>1:
     max_batch=max(1,batch_size//2)
     print(json.dumps({"event":"NOX_A5000_BATCH_OOM_REDUCE","batch_size":max_batch}),flush=True)
     continue
    print(json.dumps({"event":"NOX_A5000_BATCH1_OOM_PAUSE"}),flush=True)
    time.sleep(60)
    continue
   for (ident,topic,question),answer in zip(subset,responses):
    if len(answer)<100:continue
    record={"id":ident,"topic":topic,"prompt":question,"text":answer,"teacher":"Qwen3.5-9B",
      "source_model":str(mod.BASE),"method":"CUDA_BATCHED_TEACHER_GENERATION",
      "quality":"NOT_INDEPENDENTLY_VERIFIED",
      "created_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with OUT.open("a",encoding="utf-8") as f:
     f.write(json.dumps(record,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
    seen.add(ident)
    print(json.dumps({"event":"NOX_A5000_DISTILLATION_EXAMPLE_SAVED","total":len(seen),
                      "cycle":cycle,"batch":batch_size}),flush=True)
   pos+=len(subset)
 cycle+=1
