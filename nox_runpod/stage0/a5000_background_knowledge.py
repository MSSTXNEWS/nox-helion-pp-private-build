#!/usr/bin/env python3
"""NOX A5000 independent background knowledge lane.
Immediately curates teacher examples on CPU; optional second QLoRA training
only with substantial free VRAM and no conflicting target checkpoint.
All results and provenance are separate from the running primary trainer.
"""
import datetime,hashlib,json,os,pathlib,random,signal,subprocess,sys,time,fcntl
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/a5000_knowledge_background"
D=R/"distillation"
P=R/"checkpoints/NOX_A5000_BACKGROUND_KNOWLEDGE"
STOP=S/"STOP"
for d in (S,D,P):d.mkdir(parents=True,exist_ok=True)
def report(event,**kw):
 x={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"event":event,**kw}
 with (S/"events.jsonl").open("a",encoding="utf-8") as f:
  f.write(json.dumps(x,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
 print(json.dumps(x,ensure_ascii=False),flush=True)
def gpu():
 try:
  v=subprocess.check_output(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu","--format=csv,noheader,nounits"],text=True,timeout=15).strip().splitlines()[0]
  a=[int(x.strip()) for x in v.split(",")]
  return dict(util=a[0],used_mib=a[1],total_mib=a[2],free_mib=a[2]-a[1],temp_c=a[3])
 except Exception as e:return {"error":str(e)[:150]}
def compile_corpus():
 # Atomic deterministic rebuild of *derived* data; never modify teacher data.
 # Split by hash to avoid train/eval leakage and avoid empty blind loops.
 candidates=sorted(D.glob("*.jsonl"))
 train={};val={}
 for p in candidates:
  if p.name.startswith("NOX_A5000_CURATED_"):continue
  if p.stat().st_size>250_000_000:continue
  try:
   with p.open(encoding="utf-8") as f:
    for line in f:
     if len(line)>500000:continue
     try:r=json.loads(line)
     except (ValueError,TypeError):continue
     if not isinstance(r,dict):continue
     body=str(r.get("text") or "").strip()
     if len(body)<90 or len(body)>120000:continue
     source=str(r.get("teacher") or r.get("origin") or p.name)[:150]
     ident=hashlib.sha256(body.encode()).hexdigest()
     obj={"id":ident,"text":body,"teacher":source,"source_file":p.name,
          "status":"SYNTHETIC_UNVERIFIED","verified":False}
     if int(ident[:8],16)%10==0:val[ident]=obj
     else:train[ident]=obj
  except OSError as e:report("SOURCE_READ_FAILED",source=p.name,error=str(e)[:150])
 for name,items in (("train",train),("holdout",val)):
  out=D/("NOX_A5000_CURATED_"+name+".jsonl")
  tmp=out.with_suffix(".jsonl.tmp")
  with tmp.open("w",encoding="utf-8") as f:
   for key in sorted(items):
    f.write(json.dumps(items[key],ensure_ascii=False)+"\n")
   f.flush();os.fsync(f.fileno())
  os.replace(tmp,out)
 return len(train),len(val),len(candidates)
def save_snapshot(c,reason):
 doc={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "samples_train":c[0],"samples_holdout":c[1],"source_files":c[2],
      "gpu":gpu(),"decision":reason,
      "primary_results":{n:len(list((R/"checkpoints"/n).glob("pass*/SUCCESS.json")))
         for n in ("NOX_PRIME_9B_GENESIS","NOX_9B_KNOWLEDGE")},
      "background_checkpoint_dir":str(P),"no_primary_checkpoint_writes":True}
 tmp=S/"snapshot.json.tmp";tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2))
 os.replace(tmp,S/"snapshot.json")
def attempt_train():
 # Actual GPU training: only after safe VRAM threshold and enough distinct data.
 # Uses isolated model adapter and checkpoints; refuses to overwrite existing.
 from importlib.util import spec_from_file_location,module_from_spec
 import torch
 source=R/"tools/nox_prime_9b.py"
 base=R/"models/NOX_9B_UNIFIED"
 if not source.exists() or not (base/"NOX_UNIFIED_RECEIPT.json").exists():
  return "WAITING_FOR_UNIFIED_NOX_BASE"
 if not torch.cuda.is_available():return "CUDA_NOT_AVAILABLE"
 g=gpu()
 if "error" in g:return "TELEMETRY_UNAVAILABLE"
 if g["free_mib"]<12500:return "WAITING_FOR_12_5GIB_FREE_VRAM"
 if g["temp_c"]>=73:return "GPU_TEMPERATURE_HOLD"
 trainfile=D/"NOX_A5000_CURATED_train.jsonl"
 records=[json.loads(x)["text"] for x in trainfile.read_text(encoding="utf-8").splitlines() if x.strip()]
 if len(records)<48:return "WAITING_FOR_48_DISTINCT_EXAMPLES"
 # Compatibility requires full 9B base, not the donor's original weights.
 spec=spec_from_file_location("nox_background_curated_trainer",str(source))
 m=module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
 m.BASE=base;m.WORK=P;m.CORPUS=D/"NOX_A5000_CURATED_tune.jsonl"
 m.CORPUS.write_text("".join(json.dumps({"text":v},ensure_ascii=False)+"\n" for v in records),encoding="utf-8")
 epochs=len(list(P.glob("pass*/SUCCESS.json")))+1
 if epochs>3:return "BACKGROUND_MAX_3_PASSES_REACHED_EVALUATION_REQUIRED"
 tok,model=m.load_4bit()
 try:
  # One complete pass, and module's internal per-pass checkpoint/auto-OOM handling.
  m.train(tok,model,epochs,512,4,16,batch_size=1)
 finally:
  del model
  torch.cuda.empty_cache()
 return "GPU_KNOWLEDGE_PASS_SAVED"
def main():
 handle=(S/"worker.lock").open("a+")
 try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  print("NOX_KNOWLEDGE_BACKGROUND_ALREADY_RUNNING",flush=True);return
 report("NOX_KNOWLEDGE_BACKGROUND_STARTED",mode="continuous CPU curation + guarded independent QLoRA")
 tries=0;last_counts=(-1,-1,-1)
 while not STOP.exists():
  try:
   counts=compile_corpus()
   if counts!=last_counts:
    report("KNOWLEDGE_CORPUS_CURATED",train=counts[0],holdout=counts[1],sources=counts[2])
    last_counts=counts
   # On each cycle, report real progress even if GPU unavailable.
   outcome="CURATED_CPU_WAITING_FOR_GPU"
   if tries<3 and counts[0]>=48:
    g=gpu()
    if g.get("free_mib",0)>=12500 and g.get("temp_c",99)<73:
     try:
      outcome=attempt_train()
      if outcome=="GPU_KNOWLEDGE_PASS_SAVED":tries+=1
     except Exception as ex:
      tries+=1
      outcome="TRAINING_HOLD_ERROR"
      report("BACKGROUND_TRAINING_EXCEPTION",reason=repr(ex)[:350],attempt=tries)
    else:outcome="GPU_MEMORY_RESERVED_FOR_PRIMARY"
   save_snapshot(counts,outcome)
   report("KNOWLEDGE_HEARTBEAT",decision=outcome)
  except Exception as ex:report("KNOWLEDGE_LOOP_EXCEPTION",reason=repr(ex)[:350])
  for _ in range(60):
   if STOP.exists():break
   time.sleep(1)
 report("BACKGROUND_EXITED_NO_PRIMARY_INTERRUPTION")
if __name__=="__main__":main()
