#!/usr/bin/env python3
"""NOX PRIME 9B Genesis: full 9B foundation inheritance, QLoRA training, optional full-weight merge.
NOX Embryo V1 is preserved as lineage, not silently treated as a compatible 9B checkpoint.
"""
import argparse,hashlib,json,os,pathlib,random,sys,time,traceback
import torch
from safetensors.torch import load_file
ROOT=pathlib.Path("/workspace/nox")
BASE=ROOT/"models/NOX_PRIME_9B_INHERITED"
EMBRYO=ROOT/"embryo/NOX_EMBRYO_TRANSFER_STAGE"
WORK=ROOT/"checkpoints/NOX_PRIME_9B_GENESIS"
CORPUS=ROOT/"distillation/nox_prime_9b_teacher.jsonl"
TOPICS=[
"Python algorithms and complexity","Python debugging","Rust ownership and error handling",
"SQL transactions and indexing","Distributed fault tolerance","Operating systems and memory management",
"Transformer attention and embeddings","Neural network training","LoRA QLoRA and distillation",
"GPU CUDA optimization and safety","RAG factual retrieval and citations","Software security and secrets handling",
"Windows PowerShell automation","Web UI accessibility and responsiveness","Scientific reasoning",
"Probability and Bayesian inference","Spanish language conversation","Russian language conversation",
"Task planning and self-correction","Code reviews and regression prevention","Long term memory systems",
"Database schema migrations","HTTP APIs and authentication","Software architecture tradeoffs"]
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
 return h.hexdigest()
def write_event(event,**kw):
 print(json.dumps({"event":event,**kw},ensure_ascii=False),flush=True)
def verify():
 assert torch.cuda.is_available(),"NVIDIA GPU is required"
 assert (EMBRYO/"embryo_manifest.json").is_file(),"Original Embryo lineage is absent"
 cfg=json.loads((BASE/"config.json").read_text(encoding="utf-8"))
 assert cfg["model_type"]=="qwen3_5","Wrong 9B architecture"
 shards=sorted(BASE.glob("*.safetensors"))
 assert len(shards)==4 and sum(p.stat().st_size for p in shards)>15_000_000_000,"Incomplete original 9B weights"
 # Verify all original weights before touching training. Never modify originals.
 manifest=BASE/"transfer_manifest.json"
 assert manifest.is_file(),"Original 9B manifest missing"
 items=json.loads(manifest.read_text(encoding="utf-8-sig"))
 for it in items:
  p=BASE/it["path"]
  assert p.is_file() and p.stat().st_size==it["size"],f"Missing original shard {p}"
  assert sha(p)==it["sha256"],f"Original SHA failure {p}"
 write_event("NOX_9B_INHERITANCE_SOURCE_VERIFIED",shards=len(shards),bytes=sum(p.stat().st_size for p in shards))
def constructors():
 from transformers import AutoTokenizer,BitsAndBytesConfig
 from transformers import AutoModelForCausalLM
 try:from transformers import Qwen3_5ForConditionalGeneration
 except ImportError:Qwen3_5ForConditionalGeneration=None
 return AutoTokenizer,BitsAndBytesConfig,AutoModelForCausalLM,Qwen3_5ForConditionalGeneration
def load_4bit():
 AutoTokenizer,BitsAndBytesConfig,Auto,Qwen=constructors()
 dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
 config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",
     bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
 opts=dict(local_files_only=True,trust_remote_code=False,
           quantization_config=config,device_map={"":0},torch_dtype=dtype)
 cls=Qwen or Auto
 tok=AutoTokenizer.from_pretrained(str(BASE),local_files_only=True,trust_remote_code=False)
 if tok.pad_token is None:tok.pad_token=tok.eos_token
 model=cls.from_pretrained(str(BASE),**opts)
 return tok,model
def create_corpus(tok,model,per_topic):
 CORPUS.parent.mkdir(parents=True,exist_ok=True)
 completed={}
 if CORPUS.exists():
  for line in CORPUS.read_text(encoding="utf-8").splitlines():
   try:
    r=json.loads(line)
    if r.get("id") and len(r.get("text",""))>=80:completed[r["id"]]=r
   except (ValueError,KeyError):pass
 model.eval()
 for topic in TOPICS:
  for iteration in range(per_topic):
   ident=hashlib.sha256((topic+"|"+str(iteration)).encode()).hexdigest()[:20]
   if ident in completed:continue
   language=["Russian","English","Spanish"][iteration%3]
   prompt=(f"Create an accurate, challenging technical question and a detailed, rigorous answer about {topic}. "
           f"Use {language}. Clearly explain reasoning, limitations, and an example. "
           "Do not invent status claims or credentials. Give original instructional content. "
           f"Exercise variant {iteration+1}.")
   messages=[{"role":"system","content":"You are an expert technical educator. Avoid fabricated external claims."},
             {"role":"user","content":prompt}]
   try:
    payload=tok.apply_chat_template(messages,add_generation_prompt=True,enable_thinking=False,
            return_tensors="pt",return_dict=True)
   except TypeError:
    payload=tok.apply_chat_template(messages,add_generation_prompt=True,return_tensors="pt")
   kwargs={"input_ids":payload.to(model.device)} if isinstance(payload,torch.Tensor) else {
       k:v.to(model.device) for k,v in payload.items() if isinstance(v,torch.Tensor)}
   with torch.inference_mode():
    ans=model.generate(**kwargs,max_new_tokens=480,do_sample=True,temperature=0.65,
                 top_p=0.9,pad_token_id=tok.eos_token_id)
   answer=tok.decode(ans[0][kwargs["input_ids"].shape[-1]:],skip_special_tokens=True).strip()
   if len(answer)<80:
    write_event("TEACHER_REJECTED_SHORT",topic=topic,variant=iteration)
    continue
   row={"id":ident,"teacher":"Qwen3.5-9B_FULL_FOUNDATION","topic":topic,"lang":language,
        "text":f"Question: {prompt}\nAnswer: {answer}","verified":"SYNTHETIC_NOT_FACT_CHECKED"}
   with CORPUS.open("a",encoding="utf-8") as out:
    out.write(json.dumps(row,ensure_ascii=False)+"\n");out.flush();os.fsync(out.fileno())
   completed[ident]=row
   if len(completed)%10==0:write_event("TEACHER_CORPUS_PROGRESS",accepted=len(completed),target=len(TOPICS)*per_topic)
 write_event("TEACHER_CORPUS_READY",count=len(completed))
 if len(completed)<48:raise RuntimeError("Insufficient genuine teacher outputs")
 return completed
def train(tok,model,epochs,context,grad_accum,rank):
 from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training
 records=[json.loads(x)["text"] for x in CORPUS.read_text(encoding="utf-8").splitlines() if x.strip()]
 records=list(dict.fromkeys(records))
 random.Random(42).shuffle(records)
 if len(records)<48:raise RuntimeError("Not enough distinct teacher records")
 WORK.mkdir(parents=True,exist_ok=True)
 lineage={"identity":"NOX_PRIME_9B","parameter_scale":"9B",
    "foundation":"all original Qwen3.5-9B weight shards inherited",
    "foundation_path":str(BASE),"original_embryo_lineage":str(EMBRYO),
    "method":"QLoRA adaptation of inherited 9B foundation",
    "not_claimed":"not an independently pretrained 9B network"}
 (WORK/"lineage.json").write_text(json.dumps(lineage,indent=2,ensure_ascii=False),encoding="utf-8")
 model.config.use_cache=False
 model=prepare_model_for_kbit_training(model)
 model=get_peft_model(model,LoraConfig(r=rank,lora_alpha=2*rank,lora_dropout=0.05,
                  target_modules="all-linear",task_type="CAUSAL_LM"))
 model.train()
 optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=6e-5)
 completed=set()
 for i in range(1,epochs+1):
  if (WORK/f"pass{i}"/"SUCCESS.json").exists():completed.add(i)
 start=max(completed,default=0)+1
 prev=WORK/f"pass{start-1}"/"adapter"
 if start>1:
  from peft import set_peft_model_state_dict
  from safetensors.torch import load_file
  weights=load_file(str(prev/"adapter_model.safetensors"),device="cpu")
  set_peft_model_state_dict(model,weights)
 best=None
 all_events=[]
 for ep in range(start,epochs+1):
  passdir=WORK/f"pass{ep}"
  passdir.mkdir(parents=True,exist_ok=True)
  optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=6e-5/(ep**1.3))
  order=list(range(len(records)));random.Random(2026+ep).shuffle(order)
  losses=[];step=0
  for idx in order:
   encoded=tok(records[idx],return_tensors="pt",truncation=True,max_length=context)
   tokens=encoded["input_ids"].to(model.device)
   masks=encoded["attention_mask"].to(model.device)
   if tokens.shape[1]<10:continue
   try:
    output=model(input_ids=tokens,attention_mask=masks,labels=tokens)
    loss=output.loss/grad_accum
    if not torch.isfinite(loss):raise RuntimeError("Non-finite loss")
    loss.backward()
    losses.append(float(loss.item())*grad_accum)
   except torch.cuda.OutOfMemoryError as exc:
    optimizer.zero_grad(set_to_none=True)
    torch.cuda.empty_cache()
    write_event("NOX_OOM_FAIL_CLOSED",epoch=ep,step=step,context=context)
    raise RuntimeError("CUDA OOM; checkpoint preserved. Lower --context for next run.") from exc
   step+=1
   if step%grad_accum==0 or step==len(order):
    torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
    optimizer.step();optimizer.zero_grad(set_to_none=True)
   if step%25==0:
    write_event("NOX_9B_TRAINING",pass_number=ep,examples=step,total=len(order),
                training_loss=sum(losses[-25:])/min(len(losses),25))
  # Persist pass weights before starting the next pass
  tmp=passdir/"adapter_temp"
  model.save_pretrained(str(tmp),safe_serialization=True)
  final=passdir/"adapter"
  if final.exists():raise RuntimeError("Existing finalized adapter not overwritten")
  os.rename(tmp,final)
  metric=sum(losses)/len(losses)
  receipt={"status":"ADAPTER_TRAINED_NOT_INDEPENDENTLY_EVALUATED",
    "pass_number":ep,"examples":step,"mean_training_loss":metric,
    "adapter_sha256":sha(final/"adapter_model.safetensors"),
    "full_foundation_weights_preserved":True}
  (passdir/"SUCCESS.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
  write_event("NOX_PASS_SAVED",**receipt)
  if best is not None and metric>best*1.5:
   write_event("NOX_TRAINING_REGRESSION_STOP",pass_number=ep)
   break
  best=metric
 tok.save_pretrained(str(WORK/"tokenizer"))
 write_event("NOX_9B_ADAPTER_READY",result=str(WORK))
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--teacher-exercises-per-topic",type=int,default=8)
 p.add_argument("--passes",type=int,default=3)
 p.add_argument("--context",type=int,default=512)
 p.add_argument("--grad-accum",type=int,default=4)
 p.add_argument("--lora-rank",type=int,default=32)
 a=p.parse_args()
 if not 1<=a.teacher_exercises_per_topic<=100:raise RuntimeError("Invalid teacher count")
 if not 1<=a.passes<=3:raise RuntimeError("Invalid passes")
 verify()
 tok,model=load_4bit()
 create_corpus(tok,model,a.teacher_exercises_per_topic)
 del model
 torch.cuda.empty_cache()
 tok,model=load_4bit()
 train(tok,model,a.passes,a.context,a.grad_accum,a.lora_rank)
if __name__=="__main__":
 try:main()
 except Exception as ex:
  write_event("NOX_GENESIS_FAILED",reason=str(ex),trace=traceback.format_exc()[-2500:])
  raise
