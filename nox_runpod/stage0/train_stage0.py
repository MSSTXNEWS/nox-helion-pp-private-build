#!/usr/bin/env python3
"""NOX PRIME 9B stage 0: real, guarded QLoRA adaptation of the local Qwen3.5-9B checkpoint.
No teacher distillation until a real teacher/dataset and validation pipeline exist.
"""
import argparse
import json
import pathlib
import signal

stop_requested = False
def _stop(*_):
    global stop_requested
    stop_requested = True
signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Path to TRANSFERRED AND VERIFIED local NOX_PRIME_9B_INHERITED directory")
    ap.add_argument("--data", required=True, help="Approved JSONL, each record has a nonempty 'text' field")
    ap.add_argument("--out", required=True, help="Persistent checkpoint directory")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--save-steps", type=int, default=5)
    ap.add_argument("--seq-len", type=int, default=256)
    ap.add_argument("--epochs", type=int, default=3)
    args = ap.parse_args()
    modeldir = pathlib.Path(args.model)
    if not modeldir.is_dir() or not (modeldir / "config.json").exists():
        ap.error("Missing local NOX model directory/config.json; do not substitute public base weights")
    cfg = json.loads((modeldir / "config.json").read_text(encoding="utf-8"))
    if cfg.get("model_type") != "qwen3_5":
        ap.error("Expected qwen3_5 architecture; refusing incompatible model")
    shards = sorted(modeldir.glob("*.safetensors"))
    if len(shards) != 4 or sum(p.stat().st_size for p in shards) < 15_000_000_000:
        ap.error("Expected four full safetensors shards (>15 GB); incomplete transfer")
    if not (1 <= args.max_steps <= 1000000) or not (1 <= args.save_steps <= args.max_steps) or not (1<=args.epochs<=10):
        ap.error("invalid steps for pilot")
    data_path = pathlib.Path(args.data)
    if not data_path.is_file():
        ap.error("Explicit user-approved training JSONL missing")
    texts = []
    for n, line in enumerate(data_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj,dict) or not isinstance(obj.get("text"),str) or not obj["text"].strip():
            ap.error(f"invalid text at line {n}")
        texts.append(obj["text"])
    if len(texts) < 2:
        ap.error("need at least two real approved examples")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("No CUDA GPU, refusing fallback to CPU")
    from datasets import Dataset
    from transformers import (
        AutoTokenizer, Qwen3_5ForConditionalGeneration, BitsAndBytesConfig,
        Trainer, TrainingArguments, TrainerCallback, DataCollatorForLanguageModeling,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"event":"preflight","cuda_gpu":torch.cuda.get_device_name(0),
                      "architecture":cfg["model_type"],"weight_shards":len(shards),
                      "examples":len(texts),"status":"NOT_TRAINED"}),flush=True)
    tokenizer=AutoTokenizer.from_pretrained(str(modeldir),trust_remote_code=False,local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model=Qwen3_5ForConditionalGeneration.from_pretrained(
        str(modeldir), local_files_only=True, trust_remote_code=False,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16),
        device_map={"":0}
    )
    model.config.use_cache = False
    model=prepare_model_for_kbit_training(model)
    model=get_peft_model(model, LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,
        target_modules=["q_proj","k_proj","v_proj","o_proj"],task_type="CAUSAL_LM"))
    dataset=Dataset.from_dict({"text":texts}).map(
        lambda b:tokenizer(b["text"],truncation=True,max_length=args.seq_len),
        batched=True,remove_columns=["text"])
    class StopAndSave(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if stop_requested:
                control.should_save=True
                control.should_training_stop=True
            return control
    train_args=TrainingArguments(
        output_dir=str(out),max_steps=args.max_steps,save_steps=args.save_steps,
        per_device_train_batch_size=1,gradient_accumulation_steps=4,
        learning_rate=5e-5,logging_steps=1,report_to="none",
        save_total_limit=3,gradient_checkpointing=True,
        bf16=torch.cuda.is_bf16_supported(),fp16=not torch.cuda.is_bf16_supported(),
        optim="paged_adamw_8bit",remove_unused_columns=False)
    trainer=Trainer(model=model,args=train_args,train_dataset=dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer,mlm=False),
        callbacks=[StopAndSave()])
    ckpts=sorted(out.glob("checkpoint-*"),key=lambda p:int(p.name.split("-")[-1]))
    trainer.train(resume_from_checkpoint=str(ckpts[-1]) if ckpts else None)
    final=out/"adapter_unvalidated"
    trainer.save_model(str(final))
    tokenizer.save_pretrained(str(final))
    (out/"result.json").write_text(json.dumps({
        "status":"TRAINED_NOT_VALIDATED","steps":trainer.state.global_step,
        "model_path":str(modeldir),"dataset_count":len(texts),
        "interrupted":stop_requested,"adapter_path":str(final)
    },indent=2),encoding="utf-8")
    print("TRAINED_NOT_VALIDATED - NOT DISTILLED; do not auto-activate in NOX",flush=True)

if __name__ == "__main__":
    main()
