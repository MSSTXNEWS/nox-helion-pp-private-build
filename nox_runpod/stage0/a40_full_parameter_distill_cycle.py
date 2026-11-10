#!/usr/bin/env python3
"""NOX full-parameter, adapter-free 9B teacher->student distillation; A40 ONLY.

All student parameters are updated (no PEFT/LoRA, no quantized optimizer),
with bf16 and factored Adafactor for reduced optimizer state memory. One full
checkpoint written at END of the bounded cycle, checked by SHA-256 and tested
on held-out examples. Progress % describes THIS measurable cycle, not total
knowledge transfer. A HOLD/ERROR is never 100%.
"""
import argparse,datetime,fcntl,hashlib,json,math,os,pathlib,shutil,sqlite3,sys,time,traceback
ROOT=pathlib.Path("/workspace/nox")
STATE=ROOT/"dispatcher/a40_full_parameter"
BASE=ROOT/"models/NOX_9B_UNIFIED"
MEMORY=ROOT/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
DEST=pathlib.Path("/opt/nox_full_parameter_A40")
STATE.mkdir(parents=True,exist_ok=True)
DEST.mkdir(parents=True,exist_ok=True)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(name,obj):
 path=STATE/name;tmp=path.with_suffix(path.suffix+".tmp")
 with tmp.open("w",encoding="utf8") as f:
  json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def report(status,stage,steps=0,target=20,loss=None,holdout=None,reason="",extra=None):
 # % is a finite verified work plan. Full model checkpoint and test gate are last 10%.
 pct=min(90,round(90*steps/target,2))
 if stage=="CHECKPOINT_SHA256_VERIFIED":pct=95
 if status=="COMPLETE_VERIFIED":pct=100
 obj={"utc":utc(),"status":status,"stage":stage,"cycle_progress_percent":pct,
      "steps_executed_this_cycle":steps,"target_steps_this_cycle":target,
      "last_train_loss":loss,"holdout_loss":holdout,"reason":reason,
      "all_teacher_knowledge_absorbed_percent":None,
      "no_adapters":True,"training_method":"FULL_PARAMETER_BF16_CHUNKED_ADAFACTOR",
      "student_weight_promotion":"FULL_CHECKPOINT_ONLY",
      "extra":extra or {}}
 write("progress.json",obj)
 print(json.dumps(obj,ensure_ascii=False),flush=True)
def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for data in iter(lambda:f.read(8*1024*1024),b""):h.update(data)
 return h.hexdigest()
def samples():
 if not MEMORY.exists():raise RuntimeError("NOX_S03_MEMORY_DB_MISSING")
 c=sqlite3.connect("file:"+str(MEMORY)+"?mode=ro",uri=True,timeout=10)
 try:
  rows=c.execute("SELECT content, teacher, content_sha FROM knowledge WHERE teacher != 'UNATTRIBUTED'").fetchall()
 finally:c.close()
 train=[];test=[];teachers={}
 for text,teacher,h in rows:
  if not isinstance(text,str) or len(text)<100 or len(text)>4000:continue
  if sha256text(text)!=h:continue
  rec=(text,teacher,h)
  teachers[teacher]=teachers.get(teacher,0)+1
  if int(h[:8],16)%10==0:test.append(rec)
  else:train.append(rec)
 # deterministic partition, never mix holdout into training.
 if len(train)<32 or len(test)<4:raise RuntimeError("HOLD_INSUFFICIENT_DISTINCT_TRAIN_OR_HOLDOUT_SAMPLES")
 if not teachers:raise RuntimeError("HOLD_NO_ATTRIBUTED_TEACHER_SAMPLES")
 return train,test,teachers
def sha256text(t):return hashlib.sha256(t.encode("utf8")).hexdigest()
def load_model():
 import torch
 from transformers import AutoTokenizer
 try:
  from transformers import Qwen3_5ForConditionalGeneration as Class
 except ImportError:
  from transformers import AutoModelForCausalLM as Class
 # Never load a PEFT adapter or quantized 4-bit training model.
 # Resume only from an accepted, full-size SHA-verified student checkpoint.
 override=os.environ.get("NOX_STUDENT_BASE")
 if override:
  base=pathlib.Path(override)
 else:
  candidates=[]
  for receipt_path in DEST.glob("*/NOX_FULL_TRAIN_RECEIPT.json"):
   try:
    doc=json.loads(receipt_path.read_text(encoding="utf8"))
    if doc.get("status")!="FULL_PARAMETER_ADAPTER_FREE_STUDENT_CHECKPOINT_SAVED_NOT_ALL_KNOWLEDGE_ABSORBED":
     continue
    if float(doc.get("after_holdout_loss",float("inf")))>float(doc.get("baseline_holdout_loss",0))*1.05:
     continue
    candidates.append((receipt_path.stat().st_mtime_ns,receipt_path.parent))
   except (OSError,ValueError,TypeError):continue
  # Use only the latest proven full-weight checkpoint, not another teacher/model.
  base=max(candidates,key=lambda x:x[0])[1] if candidates else BASE
 if not base.is_dir():raise RuntimeError("NOX_STUDENT_BASE_DIRECTORY_MISSING")
 receipt=base/("NOX_FULL_TRAIN_RECEIPT.json" if (base/"NOX_FULL_TRAIN_RECEIPT.json").exists() else "NOX_UNIFIED_RECEIPT.json")
 if not receipt.is_file():raise RuntimeError("NOX_UNIFIED_FULL_BASE_NOT_VERIFIED")
 info=json.loads(receipt.read_text(encoding="utf8"))
 shards=info.get("shards",[])
 if not shards:raise RuntimeError("HOLD_BASE_SHARDS_UNDOCUMENTED")
 for shard in shards:
  p=base/shard["file"]
  if not p.is_file() or p.stat().st_size!=int(shard.get("size",shard.get("bytes",-1))):
   raise RuntimeError("BASE_SHARD_MISSING")
  if shard.get("sha256") and sha(p)!=shard["sha256"]:
   raise RuntimeError("BASE_SHARD_SHA256_MISMATCH")
 tok=AutoTokenizer.from_pretrained(str(base),local_files_only=True,trust_remote_code=False)
 if tok.pad_token_id is None:tok.pad_token=tok.eos_token
 opts={"local_files_only":True,"trust_remote_code":False,
        "dtype":torch.bfloat16,"low_cpu_mem_usage":True}
 try:mod=Class.from_pretrained(str(base),**opts)
 except TypeError:
  opts["torch_dtype"]=opts.pop("dtype")
  mod=Class.from_pretrained(str(base),**opts)
 return tok,mod
def loss_for(mod,tok,text,training=True):
 import torch
 inputs=tok(text,return_tensors="pt",truncation=True,max_length=48)
 ids=inputs["input_ids"].to("cuda",non_blocking=True)
 mask=inputs.get("attention_mask")
 if mask is not None:mask=mask.to("cuda",non_blocking=True)
 # Forward must provide gradients only in training.
 kwargs={"input_ids":ids,"labels":ids}
 if mask is not None:kwargs["attention_mask"]=mask
 out=mod(**kwargs)
 return out.loss
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--steps",type=int,default=20)
 parser.add_argument("--lr",type=float,default=1e-5)
 parser.add_argument("--cycle",type=str,required=True)
 a=parser.parse_args()
 if a.steps<1 or a.steps>500:raise RuntimeError("STEPS_OUT_OF_BOUNDS")
 if not a.cycle.replace("_","").isalnum() or len(a.cycle)>50:raise RuntimeError("INVALID_CYCLE_ID")
 if not (0<a.lr<=5e-5):raise RuntimeError("UNSAFE_LEARNING_RATE")
 lk=(STATE/"trainer.lock").open("a+")
 try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print("NOX_FULL_PARAMETER_TRAINER_ALREADY_RUNNING",flush=True);return
 import torch
 if not torch.cuda.is_available() or "A40" not in torch.cuda.get_device_name(0):
  report("HOLD","CUDA_PREFLIGHT",target=a.steps,reason="A40_REQUIRED");return
 if not hasattr(torch.optim,"Adafactor"):
  report("HOLD","OPTIMIZER_PREFLIGHT",target=a.steps,reason="TORCH_FACTORED_ADAFACTOR_UNAVAILABLE");return
 free,tot=torch.cuda.mem_get_info()
 if free<37*1024**3:
  report("HOLD","GPU_PREFLIGHT",target=a.steps,reason="NEED_AT_LEAST_37_GIB_FREE_VRAM",
    extra={"free_gib":round(free/1024**3,2)});return
 if shutil.disk_usage("/opt").free<23*1024**3:
  report("HOLD","DISK_PREFLIGHT",target=a.steps,reason="NEED_23_GIB_CONTAINER_DISK_FOR_FULL_WEIGHTS");return
 mem={}
 for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
  if line.startswith("MemAvailable:"):mem["available_gib"]=int(line.split()[1])//1048576
 if mem.get("available_gib",0)<24:
  report("HOLD","CPU_RAM_PREFLIGHT",target=a.steps,reason="NEED_24_GIB_FREE_CPU_RAM",extra=mem);return
 try:train,test,teachers=samples()
 except Exception as e:
  report("HOLD","DATA_PREFLIGHT",target=a.steps,reason=str(e)[:250]);return
 if a.cycle.startswith("v3_"):
  prior=STATE/"v3_last_accepted_teacher_counts.json"
  if prior.is_file():
   try:
    previous=json.loads(prior.read_text())
    if not any(teachers.get(t,0)>int(previous.get(t,0)) for t in teachers):
     report("HOLD","NEW_TEACHER_DATA_REQUIRED",target=a.steps,
            reason="NO_NEW_TEACHER_EXAMPLES_SINCE_LAST_ACCEPTED_CYCLE")
     return
   except (ValueError,TypeError):
    raise RuntimeError("HOLD_INVALID_LAST_TEACHER_COUNTS")
 report("RUNNING","FULL_PARAMETER_MODEL_LOADING",target=a.steps,extra={"train_examples":len(train),"holdout_examples":len(test),"teacher_counts":teachers})
 # At most one live full checkpoint on container disk. Never overwrite any prior artifact.
 output=DEST/("NOX_FULL_CYCLE_"+a.cycle+"_STEP_"+str(a.steps))
 if output.exists():
  report("HOLD","OUTPUT_EXISTS",target=a.steps,reason="EXISTING_FULL_CHECKPOINT_PRESERVED")
  return
 tok,mod=load_model()
 mod.to("cuda")
 mod.train()
 mod.config.use_cache=False
 try:mod.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant":False})
 except TypeError:mod.gradient_checkpointing_enable()
 for p in mod.parameters():p.requires_grad_(True)
 total_params=sum(p.numel() for p in mod.parameters())
 trainable=sum(p.numel() for p in mod.parameters() if p.requires_grad)
 if total_params!=trainable or total_params<8_000_000_000:
  raise RuntimeError("NOT_ALL_9B_PARAMETERS_TRAINABLE")
 # Split the optimizer into small weight views. Adafactor's unfactored
 # intermediate on the largest 9B tensor caused a 1.89 GiB CUDA OOM.
 # Each view shares physical storage with the ORIGINAL NOX weights.
 # The optimizer has state per view, not an adapter or secondary network.
 source_params=list(mod.parameters())
 slices=[]
 small=[]
 max_elements=1_000_000
 for p in source_params:
  if not p.requires_grad:continue
  if p.ndim==0:
   view=torch.nn.Parameter(p.data,requires_grad=True)
   slices.append((p,view,None,None))
   small.append(view)
   continue
  row_elements=p.numel()//max(1,p.shape[0])
  rows=max(1,max_elements//max(1,row_elements))
  for begin in range(0,p.shape[0],rows):
   length=min(rows,p.shape[0]-begin)
   view=torch.nn.Parameter(p.data.narrow(0,begin,length),requires_grad=True)
   slices.append((p,view,begin,length))
   small.append(view)
 opt=torch.optim.Adafactor(small,lr=a.lr,weight_decay=0.0,foreach=False)
 report("RUNNING","CHUNKED_FULL_PARAMETER_OPTIMIZER_READY",target=a.steps,
        extra={"source_parameters":total_params,"optimizer_views":len(small),
               "optimizer_max_elements":max_elements,"no_adapters":True})
 # Verify that at least one sample not used for training predicts an actual loss.
 mod.eval()
 with torch.inference_mode():
  baseline=float(loss_for(mod,tok,test[0][0]).detach().float().item())
 mod.train()
 lastloss=None
 # Every completed optimizer step is attributed to the actual teacher chosen.
 teacher_names=sorted(set(x[1] for x in train))
 buckets={t:[x for x in train if x[1]==t] for t in teacher_names}
 used_teacher_counts={t:0 for t in teacher_names}
 cycle_started=time.monotonic()
 completed=0
 interrupted=False
 stop_marker=ROOT/"dispatcher/nox_v3/STOP_A40"
 hold_marker=ROOT/"dispatcher/nox_v3/HOLD_A40"
 for step in range(1,a.steps+1):
  if stop_marker.exists() or hold_marker.exists():
   interrupted=True
   break
  teacher=teacher_names[(step-1)%len(teacher_names)]
  examples=buckets[teacher]
  text=examples[((step-1)//len(teacher_names))%len(examples)][0]
  # The original model accumulates actual gradients. They are exposed as
  # views to the per-chunk Adafactor optimizer without allocating full-size
  # Adafactor intermediates on the GPU.
  for p in source_params:p.grad=None
  loss=loss_for(mod,tok,text)
  if not torch.isfinite(loss).item():raise RuntimeError("NONFINITE_TRAINING_LOSS")
  loss.backward()
  with torch.no_grad():
   for p,v,begin,length in slices:
    if p.grad is None:
     v.grad=None
    elif begin is None:
     v.grad=p.grad.detach()
    else:
     v.grad=p.grad.narrow(0,begin,length).detach()
   opt.step()
   for p,v,_,_ in slices:v.grad=None
   for p in source_params:p.grad=None
  completed=step
  used_teacher_counts[teacher]+=1
  lastloss=float(loss.detach().float().item())
  elapsed=max(time.monotonic()-cycle_started,0.001)
  report("RUNNING","REAL_ALL_PARAMETER_OPTIMIZER_STEPS",steps=step,target=a.steps,loss=lastloss,
         extra={"trainable_parameters":trainable,"available_teacher_counts":teachers,
                "optimizer_steps_by_teacher":used_teacher_counts.copy(),
                "steps_per_hour":round(step/elapsed*3600,3),
                "eta_seconds":round((a.steps-step)*elapsed/step,1),
                "student_base":str(pathlib.Path(os.environ.get("NOX_STUDENT_BASE",str(BASE))))})
 if completed==0:
  report("HOLD","SAFE70_BEFORE_FIRST_OPTIMIZER_STEP",target=a.steps,
         reason="STOP_OR_HOLD_MARKER_PRESENT")
  return
 # Interrupted but useful partial full-weight checkpoints identify the actual
 # number of completed steps, not the original requested target.
 if completed!=a.steps:
  output=DEST/("NOX_FULL_CYCLE_"+a.cycle+"_STEP_"+str(completed))
  if output.exists():
   report("HOLD","PARTIAL_OUTPUT_EXISTS",steps=completed,target=a.steps,
          reason="PRESERVE_EXISTING_PARTIAL_CHECKPOINT")
   return
 # Last 10% is proof of durable full model save and evaluation, not a fake progress increment.
 mod.eval()
 with torch.inference_mode():
  after=float(loss_for(mod,tok,test[0][0]).detach().float().item())
 if not math.isfinite(after):raise RuntimeError("NONFINITE_HOLDOUT_LOSS")
 report("RUNNING","FULL_MODEL_STAGING",steps=completed,target=a.steps,loss=lastloss,holdout=after)
 stage=DEST/("._WRITING_"+a.cycle+"_STEP_"+str(completed))
 if stage.exists():raise RuntimeError("EXISTING_INCOMPLETE_STAGE_NOT_OVERWRITTEN")
 stage.mkdir()
 try:
  mod.save_pretrained(str(stage),safe_serialization=True,max_shard_size="4GB")
  tok.save_pretrained(str(stage))
  shards=sorted(stage.glob("*.safetensors"))
  if not shards or sum(p.stat().st_size for p in shards)<14*1024**3:
   raise RuntimeError("FULL_WEIGHT_SHARDS_INCOMPLETE")
  hashes=[{"file":p.name,"bytes":p.stat().st_size,"sha256":sha(p)} for p in shards]
  receipt={"status":"FULL_PARAMETER_ADAPTER_FREE_STUDENT_CHECKPOINT_SAVED_NOT_ALL_KNOWLEDGE_ABSORBED",
     "utc":utc(),"cycle":a.cycle,"steps":completed,"planned_steps":a.steps,
     "interrupted_for_safe70":interrupted,"parameter_count":total_params,
     "teacher_counts":teachers,"optimizer_steps_by_teacher":used_teacher_counts,
     "train_examples":len(train),
     "holdout_examples":len(test),"baseline_holdout_loss":baseline,
     "after_holdout_loss":after,"no_adapter_training":True,"shards":hashes,
     "ephemeral_container_disk":True,"needs_windows_backup":True}
  write("last_cycle_receipt.json",receipt)
  with (stage/"NOX_FULL_TRAIN_RECEIPT.json").open("w",encoding="utf-8") as f:
   json.dump(receipt,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  # Atomic promote only after all shards hashed; never touch existing source base.
  os.replace(stage,output)
 except Exception:
  print("NOX_FULL_STAGE_PRESERVED_ON_ERROR",stage,flush=True)
  raise
 if interrupted:
  report("HOLD","SAFE70_INTERRUPTED_FULL_WEIGHTS_SAVED",
         steps=completed,target=a.steps,loss=lastloss,holdout=after,
         reason="STOP_OR_HOLD_MARKER_AFTER_STEP",
         extra={"checkpoint_candidate":str(output),"windows_transfer_requires_review":True})
  return
 if after>baseline*1.05:
  report("HOLD","FULL_WEIGHTS_SAVED_BUT_REJECTED_BY_HOLDOUT",
         steps=a.steps,target=a.steps,loss=lastloss,holdout=after,
         reason="HOLDOUT_REGRESSION_MORE_THAN_5_PERCENT",
         extra={"output_candidate_not_promoted":str(output),"baseline_holdout_loss":baseline,
                "checkpoint_shards":hashes,"requires_review":True})
  return
 if a.cycle.startswith("v3_"):
  tmp=STATE/"v3_last_accepted_teacher_counts.json.tmp"
  with tmp.open("w",encoding="utf-8") as f:
   json.dump(teachers,f,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(tmp,STATE/"v3_last_accepted_teacher_counts.json")
 report("COMPLETE_VERIFIED","FULL_WEIGHTS_SAVED_AND_HOLDOUT_EVALUATED",
        steps=a.steps,target=a.steps,loss=lastloss,holdout=after,
        extra={"output":str(output),"checkpoint_shards":hashes,
          "optimizer_steps_by_teacher":used_teacher_counts,
          "holdout_loss_better_than_baseline":after<=baseline,
          "not_validated_all_three_teacher_absorption":True})
if __name__=="__main__":
 try:main()
 except Exception as exc:
  report("ERROR","FULL_PARAMETER_CYCLE_FAILED",reason=str(exc)[:320],
         extra={"trace":traceback.format_exc()[-1000:]})
  raise
