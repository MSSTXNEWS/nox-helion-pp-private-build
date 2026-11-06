"""Actual GPU QLoRA, staged 1 -> 2 -> 3, only on approved rights-cleared data.

No synthetic training claims. Leaves previous adapter intact if evaluation worsens.
Python 3.11, NVIDIA CUDA, torch, transformers, peft, bitsandbytes, accelerate.
"""
from __future__ import annotations
import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
from soul_gpu import root_path, GB, TOTAL_GB, RESERVE_GB

MODEL = "Qwen/Qwen3-4B-Instruct-2507"

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def dataset(path: Path) -> tuple[list, set]:
    if not path.is_file(): raise ValueError(f"Dataset missing: {path}")
    rows, sources, hashes = [], set(), set()
    with path.open("r",encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if not line.strip():continue
            record = json.loads(line)
            if record.get("approved_for_training") is not True:
                raise PermissionError(f"Dataset row {n} lacks owner training approval")
            source = record.get("source_id")
            license_name = record.get("license")
            if not isinstance(source,str) or not source or not isinstance(license_name,str) or not license_name:
                raise ValueError(f"Row {n}: source ID + license required")
            messages = record.get("messages")
            if not isinstance(messages,list) or not messages or any(
                    not isinstance(m,dict) or m.get("role") not in ("user","assistant","system") or
                    not isinstance(m.get("content"),str) or not m["content"].strip() for m in messages):
                raise ValueError(f"Row {n}: valid conversations required")
            if messages[-1]["role"] != "assistant":
                raise ValueError(f"Row {n}: expected assistant completion")
            canonical = json.dumps(messages,ensure_ascii=False,sort_keys=True)
            digest = hashlib.sha256(canonical.encode()).hexdigest()
            if digest in hashes: raise ValueError(f"Duplicate conversation at row {n}")
            hashes.add(digest)
            sources.add(source)
            rows.append(record)
            if len(rows)>300000: raise ValueError("Dataset too large; split into another block")
    if not rows:raise ValueError("Empty training dataset")
    return rows, sources

def preflight(stage: int, root: Path) -> dict:
    if stage not in range(1,100): raise ValueError("Stage 1..99")
    block = root / "blocks" / f"block-{stage}"
    train_path = block / "train.jsonl"
    holdout_path = root / "datasets" / "holdout.jsonl"
    permit = root / "datasets" / "owner_approval.json"
    if not permit.is_file(): raise PermissionError("Missing rights/approval manifest")
    consent = read_json(permit)
    if consent.get("owner_approved") is not True or consent.get("training_allowed") is not True:
        raise PermissionError("Owner training approval not granted")
    train, train_sources = dataset(train_path)
    holdout, holdout_sources = dataset(holdout_path)
    if train_sources.intersection(holdout_sources):
        raise ValueError("TRAIN/HOLDOUT LEAKAGE: shared source IDs")
    allowed = set(consent.get("approved_source_ids",[]))
    if not train_sources.issubset(allowed) or not holdout_sources.issubset(allowed):
        raise PermissionError("Missing explicit source authorization")
    if stage > 1:
        previous = root / "adapters" / f"stage-{stage-1}"
        if not (previous / "adapter_config.json").exists() or not (previous / "TRAINING_EVIDENCE.json").exists():
            raise ValueError("Previous verified adapter is missing")
        if read_json(previous / "TRAINING_EVIDENCE.json").get("status") != "holdout-passed":
            raise ValueError("Previous stage did not pass holdout evaluation")
    free = shutil.disk_usage(root).free
    # Reserve room for base-model cache, optimizer, temporary outputs and the 60 GB safety floor.
    if free < (RESERVE_GB + 20) * GB:
        raise ValueError("Must preserve 60 GB free after up to 20 GB training/model cache")
    used = sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    if used >= TOTAL_GB * GB:
        raise ValueError("SOUL storage budget >=270 GB")
    return {"train":train,"holdout":holdout,"train_sources":sorted(train_sources),"holdout_sources":sorted(holdout_sources),
            "stage":stage,"block":block,"used_bytes":used,"free_bytes":free}

def file_sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(4*1024*1024),b""):
            h.update(part)
    return h.hexdigest()

def train(stage: int, root: Path, max_steps: int, max_length: int, gpu_fraction: float):
    prep=preflight(stage,root)
    # Keep HF weights strictly inside the managed NOX directory. External env overrides
    # would make the 270 GB accounting unverifiable.
    # One canonical HF base model cache in the 70 GB intelligence allocation.
    intelligence = root.parent / "brain" / "intelligence"
    intelligence.mkdir(parents=True, exist_ok=True)
    current = sum(p.stat().st_size for p in intelligence.rglob("*") if p.is_file() and not p.is_symlink())
    if current + 9 * GB > 70 * GB:
        raise ValueError("Intelligence 70GB quota cannot accommodate the training base cache")
    hf_cache = intelligence / "hf_cache"
    os.environ["HF_HOME"] = str(hf_cache)
    os.environ["HF_HUB_CACHE"] = str(hf_cache / "hub")
    if not 0.4<=gpu_fraction<=0.70 or not 1<=max_steps<=20000 or not 128<=max_length<=2048:
        raise ValueError("Unsafe resource parameters")
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments, DataCollatorForLanguageModeling
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
    except ImportError as exc:
        raise RuntimeError("Install CUDA torch, transformers, accelerate, bitsandbytes, peft") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("NVIDIA CUDA GPU required; never silently train on CPU")
    props=torch.cuda.get_device_properties(0)
    vram_gb=props.total_memory/1024**3
    if vram_gb<7.5: raise RuntimeError("QLoRA safety gate: >=8 GB VRAM for recommended Qwen3-4B")
    # VRAM allocator limit is NOT a cap on GPU compute utilization or physical power.
    torch.cuda.set_per_process_memory_fraction(gpu_fraction,0)
    import math as _math
    cpu_threads=max(1,_math.floor((os.cpu_count() or 2)*0.65))
    os.environ["OMP_NUM_THREADS"]=str(cpu_threads)
    os.environ["MKL_NUM_THREADS"]=str(cpu_threads)
    os.environ["TOKENIZERS_PARALLELISM"]="false"
    torch.set_num_threads(cpu_threads)
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=False)
    if tokenizer.pad_token is None:tokenizer.pad_token=tokenizer.eos_token
    config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
    model=AutoModelForCausalLM.from_pretrained(MODEL,quantization_config=config,device_map={"":0},
                                               torch_dtype=dtype,trust_remote_code=False)
    model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True)
    if stage==1:
        peft_cfg=LoraConfig(r=16,lora_alpha=32,lora_dropout=0.05,bias="none",task_type="CAUSAL_LM",
                            target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"])
        model=get_peft_model(model,peft_cfg)
    else:
        model=PeftModel.from_pretrained(model,str(root/"adapters"/f"stage-{stage-1}"),is_trainable=True)
    from torch.utils.data import Dataset
    class ConversationDataset(Dataset):
        def __init__(self,records):
            self.samples=[]
            for record in records:
                text=tokenizer.apply_chat_template(record["messages"],tokenize=False,add_generation_prompt=False)
                tokens=tokenizer(text,truncation=True,max_length=max_length,add_special_tokens=False)
                if len(tokens["input_ids"])<6:raise ValueError("Training sample shorter than six tokens")
                self.samples.append(tokens)
        def __len__(self):return len(self.samples)
        def __getitem__(self,i):return self.samples[i]
    train_data=ConversationDataset(prep["train"])
    eval_data=ConversationDataset(prep["holdout"])
    prior= root/"adapters"/f"stage-{stage}"
    if prior.exists():raise FileExistsError("Stage already trained. Never overwrite accepted adapter")
    work=root/"adapters"/f"stage-{stage}.pending"
    if work.exists():raise FileExistsError("Pending stage exists; review before retraining")
    work.mkdir(parents=True)
    kwargs=dict(output_dir=str(work/"trainer"),per_device_train_batch_size=1,per_device_eval_batch_size=1,
                gradient_accumulation_steps=8,gradient_checkpointing=True,learning_rate=0.0001,
                max_steps=max_steps,logging_steps=10,save_strategy="no",report_to="none",fp16=dtype==torch.float16,
                bf16=dtype==torch.bfloat16,dataloader_num_workers=0,remove_unused_columns=False)
    kwargs["eval_strategy" if "eval_strategy" in inspect.signature(TrainingArguments).parameters else "evaluation_strategy"]="no"
    options=TrainingArguments(**kwargs)
    trainer=Trainer(model=model,args=options,train_dataset=train_data,eval_dataset=eval_data,
                   data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer,mlm=False))

    # V2: factual live telemetry for the existing NOX host/WOW V7 consumer.
    # The host must explicitly integrate this file; this is NOT proof it already does.
    telemetry = root.parent / "brain" / "telemetry" / "training.json"
    telemetry.parent.mkdir(parents=True, exist_ok=True)
    import time as _time
    import subprocess as _subprocess
    def _report(payload):
        document = {"schema":"nox.training.v2", "stage":stage,
                    "requested_steps":max_steps, "model":MODEL,
                    "timestamp_utc":_time.strftime("%Y-%m-%dT%H:%M:%SZ",_time.gmtime()),
                    **payload}
        temporary=telemetry.with_suffix(".json.part")
        temporary.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(temporary,telemetry)
    from transformers import TrainerCallback
    class NOXProgress(TrainerCallback):
        """Thermal-triggered cooling, without unnecessary pauses under 65 C.

        At GPU temperature >=65 C, cool for at least 180 seconds and
        resume only when GPU temperature is <65 C. At >=80 C fail closed.
        VRAM cap 70% is NOT a hardware GPU compute/power utilization cap.
        """
        def __init__(self):
            self.actual=0
            self.safety_hold=None
            self.last_temperature=None
            self.total_paused=0.0
            self.cpu_threads=cpu_threads

        def gpu_temp(self):
            try:
                outcome=_subprocess.run(
                    ["nvidia-smi","--query-gpu=temperature.gpu",
                     "--format=csv,noheader,nounits","-i","0"],
                    capture_output=True,text=True,timeout=6,check=True)
                temperatures=[int(part.strip()) for part in outcome.stdout.splitlines()
                              if part.strip().isdigit()]
                if not temperatures:
                    raise ValueError("GPU temperature not readable")
                return max(temperatures)
            except (OSError,ValueError,_subprocess.SubprocessError) as exc:
                raise RuntimeError("GPU temperature monitoring unavailable") from exc

        def report(self,status,**fields):
            _report({"status":status, "actual_steps":self.actual,
                     "fraction":min(1,self.actual/max_steps), "gpu":props.name,
                     "gpu_temperature_c":self.last_temperature,
                     "gpu_memory_fraction_limit":gpu_fraction,
                     "cooldown_trigger_c":65, "resume_below_c":65,
                     "cooldown_min_seconds":180,
                     "cooldown_seconds":round(self.total_paused,1),
                     "cpu_thread_limit":self.cpu_threads,
                     **fields})

        def stop(self,control,reason):
            self.safety_hold=reason
            control.should_training_stop=True
            self.report("safety-hold",reason=reason)

        def on_log(self,args,state,control,logs=None,**kwargs):
            if logs is None:return
            self.actual=state.global_step
            fields={k:float(v) for k,v in logs.items()
                    if k in ("loss","grad_norm","learning_rate","eval_loss")
                    and isinstance(v,(int,float))}
            self.report("training",loss_metrics=fields)

        def on_step_end(self,args,state,control,**kwargs):
            self.actual=state.global_step
            if control.should_training_stop:return
            # The sample is taken after each step; a single step can still exceed the threshold.
            try:
                torch.cuda.synchronize(0)
                self.last_temperature=self.gpu_temp()
            except RuntimeError:
                self.stop(control,"temperature-sensor-unavailable")
                return
            if self.last_temperature>=80:
                self.stop(control,"gpu-hot-80c")
                return
            if shutil.disk_usage(root).free<RESERVE_GB*GB:
                self.stop(control,"disk-reserve")
                return
            if self.last_temperature<65:
                # No periodic pauses while the measured GPU core temperature is safe.
                self.report("training")
                return

            self.report("cooling",reason="gpu-reached-65c",pause_seconds=180)
            _time.sleep(180)
            self.total_paused+=180
            # Wait longer only if GPU has not cooled below 65 C.
            cutoff=_time.monotonic()+600
            while True:
                try:
                    self.last_temperature=self.gpu_temp()
                except RuntimeError:
                    self.stop(control,"temperature-sensor-unavailable")
                    return
                if self.last_temperature<65:
                    break
                if _time.monotonic()>=cutoff:
                    self.stop(control,"cooldown-timeout")
                    return
                if self.last_temperature>=80:
                    self.stop(control,"gpu-hot-80c")
                    return
                self.report("cooling",reason="gpu-still-65c-or-above")
                _time.sleep(15)
                self.total_paused+=15
            self.report("training-resumed")
    progress=NOXProgress()
    trainer.add_callback(progress)
    progress.report("starting")
    # This requires a readable GPU temperature sensor; do not run blind.
    progress.last_temperature=progress.gpu_temp()
    if progress.last_temperature>=65:
        raise RuntimeError("GPU >=65C before training; cool down before starting")

    before=trainer.evaluate()["eval_loss"]
    trainer.train()
    after=trainer.evaluate()["eval_loss"]
    # Evaluation on source-disjoint holdout. Relative tolerance guards catastrophic regressions,
    # but is NOT proof of superior intelligence, emotions, or reasoning.
    passed=(after<=before*1.07 and progress.actual>=max_steps and not progress.safety_hold)
    model.save_pretrained(str(work),safe_serialization=True)
    tokenizer.save_pretrained(str(work))
    evidence={"status":"holdout-passed" if passed else "holdout-regression-hold", "stage":stage,
              "base":MODEL,"train_sources":prep["train_sources"],"holdout_sources":prep["holdout_sources"],
              "train_count":len(train_data),"holdout_count":len(eval_data),"holdout_loss_before":before,
              "holdout_loss_after":after,"training_steps":progress.actual,"requested_steps":max_steps,"safety_hold":progress.safety_hold,"gpu":props.name,"vram_gb":vram_gb,
              "gpu_fraction":gpu_fraction,"cooldown_trigger_c":65,"cooldown_min_seconds":180,"cooldown_seconds":progress.total_paused,"cpu_threads":cpu_threads,"files":{p.name:file_sha(p) for p in work.glob("*.safetensors")}}
    (work/"TRAINING_EVIDENCE.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    _report({"status":"holdout-passed" if passed else "holdout-or-safety-hold","actual_steps":progress.actual,
             "holdout_loss_before":before,"holdout_loss_after":after})
    if not passed:
        raise RuntimeError("Holdout/safety gate: adapter retained as pending, not promoted")
    # Trainer temp checkpoints are disposable only within own pending workdir.
    shutil.rmtree(work/"trainer",ignore_errors=True)
    work.rename(prior)
    return evidence

if __name__=="__main__":
    p=argparse.ArgumentParser(description="NOX SOUL 3-stage local NVIDIA QLoRA")
    p.add_argument("--stage",type=int,required=True,choices=range(1,100))
    p.add_argument("--root",type=Path,default=root_path())
    p.add_argument("--max-steps",type=int,default=200)
    p.add_argument("--max-length",type=int,default=512)
    p.add_argument("--gpu-fraction",type=float,default=0.70)
    a=p.parse_args()
    print(json.dumps(train(a.stage,a.root,a.max_steps,a.max_length,a.gpu_fraction),indent=2))
