#!/usr/bin/env python3
"""NOX HELION stage-0: real QLoRA trainer. No synthetic PASS or fake checkpoints."""
import argparse, json, os, pathlib, signal, sys
STOP = False
def request_stop(signum, frame):
    global STOP
    STOP = True
signal.signal(signal.SIGTERM, request_stop)
signal.signal(signal.SIGINT, request_stop)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="Qwen/Qwen3-8B")
    p.add_argument("--data",required=True,help="JSONL with nonempty text field; user-approved data only")
    p.add_argument("--out",default="/workspace/nox/checkpoints/stage0")
    p.add_argument("--max-steps",type=int,default=50)
    p.add_argument("--seq-len",type=int,default=512)
    p.add_argument("--save-steps",type=int,default=10)
    args=p.parse_args()
    if args.max_steps < 1 or args.save_steps < 1: p.error("positive steps required")
    data_path=pathlib.Path(args.data)
    if not data_path.is_file(): p.error(f"dataset not found: {data_path}")
    texts=[]
    with data_path.open(encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if not line.strip(): continue
            try: obj=json.loads(line)
            except Exception as e: p.error(f"invalid JSON at line {n}: {e}")
            if not isinstance(obj,dict) or not isinstance(obj.get("text"),str) or not obj["text"].strip():
                p.error(f"line {n}: required nonempty text")
            texts.append(obj["text"])
    if len(texts)<2: p.error("need at least 2 approved examples")
    import torch
    if not torch.cuda.is_available(): raise RuntimeError("CUDA GPU is unavailable; refusing CPU training")
    from datasets import Dataset
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments, TrainerCallback, DataCollatorForLanguageModeling
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    print(json.dumps({"event":"hardware","device":torch.cuda.get_device_name(0),"cuda":torch.version.cuda,"examples":len(texts)}),flush=True)
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    tok=AutoTokenizer.from_pretrained(args.model,trust_remote_code=False)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    model=AutoModelForCausalLM.from_pretrained(args.model,quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,bnb_4bit_use_double_quant=True),device_map={"":0},trust_remote_code=False)
    model.config.use_cache=False
    model=prepare_model_for_kbit_training(model)
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=0.05,target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],task_type="CAUSAL_LM"))
    data=Dataset.from_dict({"text":texts})
    def tokenize(batch):
        encoded=tok(batch["text"],truncation=True,max_length=args.seq_len,padding=False)
        return encoded
    ds=data.map(tokenize,batched=True,remove_columns=["text"])
    class SafeStop(TrainerCallback):
        def on_step_end(self,training_args,state,control,**kwargs):
            if STOP:
                control.should_save=True
                control.should_training_stop=True
            return control
    ta=TrainingArguments(output_dir=str(out),max_steps=args.max_steps,per_device_train_batch_size=1,gradient_accumulation_steps=4,learning_rate=1e-4,save_steps=args.save_steps,save_strategy="steps",save_total_limit=3,logging_steps=1,report_to="none",gradient_checkpointing=True,bf16=torch.cuda.is_bf16_supported(),fp16=not torch.cuda.is_bf16_supported(),optim="paged_adamw_8bit",remove_unused_columns=False)
    trainer=Trainer(model=model,args=ta,train_dataset=ds,data_collator=DataCollatorForLanguageModeling(tok,mlm=False),callbacks=[SafeStop()])
    resume=sorted(out.glob("checkpoint-*"),key=lambda x:int(x.name.split("-")[-1]))
    trainer.train(resume_from_checkpoint=str(resume[-1]) if resume else None)
    trainer.save_model(str(out/"adapter_final"))
    tok.save_pretrained(str(out/"adapter_final"))
    with (out/"train_result.json").open("w",encoding="utf-8") as f:
        json.dump({"status":"TRAINED_NOT_VALIDATED","model":args.model,"examples":len(texts),"steps":trainer.state.global_step,"stopped":STOP,"adapter":str(out/"adapter_final")},f,indent=2)
    print("TRAINED_NOT_VALIDATED: local evaluation and approval required",flush=True)

if __name__=="__main__":main()
