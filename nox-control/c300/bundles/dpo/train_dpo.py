#!/usr/bin/env python3
"""NOX DPO (SRV K1 26.11): TRL DPOTrainer + Unsloth QLoRA r=8 от step_0075 (--init-adapter). Только в окно между раундами (GPU свободен от train!).
ref-политика = начальный step_0075 (precompute_ref_log_probs=True до первого шага), не голая база. Turing: fp16, без bf16.
Выход: ckpt_keep/cand_dpo_step_XXXX_<ts> (автообучение сторожем не трогается), затем ворота (try), отчёт ops/dpo/dpo_report.json.
Откат: ничего не заменяется; принять кандидата решают ворота p3_axis_guard (ROLLBACK по осям -2 п.п.)."""
import argparse, json, os, sys, time
W = "/workspace/nox"
ap = argparse.ArgumentParser()
ap.add_argument("--init-adapter", default=W + "/distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724")
ap.add_argument("--data", default=W + "/ops/dpo/dpo_train.jsonl"); ap.add_argument("--eval", default=W + "/ops/dpo/dpo_eval.jsonl")
ap.add_argument("--steps", type=int, default=150); ap.add_argument("--accum", type=int, default=16)
ap.add_argument("--lr", type=float, default=1e-5); ap.add_argument("--beta", type=float, default=0.1); ap.add_argument("--rpo", type=float, default=0.1)
ap.add_argument("--max-len", type=int, default=768); ap.add_argument("--dry", action="store_true", help="2 шага для проверки связки")
a = ap.parse_args()
if a.dry: a.steps = 2; a.accum = 2
import unsloth  # до transformers/peft
from unsloth import FastLanguageModel, PatchDPOTrainer
PatchDPOTrainer()
import torch
from datasets import load_dataset
from trl import DPOConfig, DPOTrainer
from peft import PeftModel
base = json.load(open(a.init_adapter + "/adapter_config.json"))["base_model_name_or_path"]
m, tok = FastLanguageModel.from_pretrained(base, max_seq_length=a.max_len, load_in_4bit=True, dtype=torch.float16)
tok = getattr(tok, "tokenizer", tok)
if tok.pad_token is None: tok.pad_token = tok.eos_token
m = PeftModel.from_pretrained(m, a.init_adapter, is_trainable=True)
ts = time.strftime("%m%d%H%M"); out = "%s/distill_v2/ckpt_keep/cand_dpo_%s" % (W, ts)
tr = load_dataset("json", data_files=a.data, split="train"); ev = load_dataset("json", data_files=a.eval, split="train")
cfg = DPOConfig(output_dir=out + "_trainer", per_device_train_batch_size=1, gradient_accumulation_steps=a.accum, max_steps=a.steps, learning_rate=a.lr,
                lr_scheduler_type="cosine", warmup_ratio=0.1, beta=a.beta, loss_type=["sigmoid", "sft"], loss_weights=[1.0, a.rpo], max_length=a.max_len,
                fp16=True, bf16=False, optim="paged_adamw_8bit", gradient_checkpointing=True, precompute_ref_log_probs=True,
                logging_steps=5, save_strategy="no", eval_strategy="no", report_to="none", seed=7)
t0 = time.time()
tr_ = DPOTrainer(model=m, ref_model=None, args=cfg, train_dataset=tr, eval_dataset=ev, processing_class=tok)
res = tr_.train()
os.makedirs(out, exist_ok=True); m.save_pretrained(out)
rep = {"out": out, "steps": a.steps, "sec": round(time.time() - t0), "loss": res.training_loss, "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20), "pairs": len(tr), "t": time.strftime("%FT%TZ", time.gmtime())}
try: rep["eval"] = tr_.evaluate()
except Exception as e: rep["eval_err"] = repr(e)[:200]
json.dump(rep, open(W + "/ops/dpo/dpo_report.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(rep, ensure_ascii=False))
