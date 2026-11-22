#!/usr/bin/env python3
"""SLP-04 train_kto_s2.py: обучение LoRA «спинного мозга» (KTO или SFT) на S2 (2xV100 32 ГБ, fp16, БЕЗ bf16).
Запускать через train_lora_s2.sh (проверка GPU, квитанция, GGUF). Новые pip: trl>=1.18 (KTOTrainer стабилен в trl, не в experimental), peft>=0.22, transformers>=5, accelerate, datasets.
Особенности V100: fp16=True, bf16=False, attn_implementation=sdpa (flash-attn 2 не работает на sm_70), адаптеры в fp32 (peft autocast), gradient checkpointing,
защита от NaN (fp16 у Qwen может переполняться): при нечисловом loss обучение останавливается, адаптер НЕ сохраняется как годный.
Для Qwen3 в строки добавляется chat_template_kwargs={enable_thinking: False} — тот же путь, что на инференсе llama.cpp (без блока рассуждений).
"""
import argparse, json, os, sys, time


def apply_weight(o, w, rnd):
    """Вес строки без правки TRL: w<1 - детерминированное прореживание, w>1 - дубли (1.5 = 1 + 50%)."""
    n = int(w) + (1 if rnd.random() < (w - int(w)) else 0)
    return n


def load_rows(path, mode):
    import random
    rnd = random.Random(7)
    rows = []
    for l in open(path, encoding="utf-8"):
        if not l.strip():
            continue
        o = json.loads(l)
        if not (isinstance(o.get("prompt"), list) and isinstance(o.get("completion"), list) and isinstance(o.get("label"), bool)):
            raise ValueError("строка не в формате KTO {prompt:[msgs], completion:[msgs], label:bool}: " + l[:80])
        if mode == "sft" and not o["label"]:
            continue
        for _ in range(apply_weight(o, float(o.get("weight", 1.0)), rnd)):
            rows.append({"prompt": o["prompt"], "completion": o["completion"], "label": o["label"], "chat_template_kwargs": {"enable_thinking": False}})
    if not rows:
        raise ValueError("пустой датасет: " + path)
    return rows


def plan(a, stats):
    eff = a.batch * a.accum * max(1, len(a.gpus.split(",")))
    return {"base": a.base, "mode": a.mode, "gpus": a.gpus, "dtype": "float16", "lora": {"r": a.rank, "alpha": a.alpha, "dropout": 0.05, "targets": "all-linear"},
            "lr": a.lr, "beta": a.beta, "epochs": a.epochs, "max_length": a.max_length, "per_device_batch": a.batch, "grad_accum": a.accum, "effective_batch": eff,
            "desirable_weight": stats.get("desirable_weight", 1.0), "undesirable_weight": stats.get("undesirable_weight", 1.0), "out": a.out}


def train(a, train_rows, eval_rows, stats):
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA недоступна")
    tok = AutoTokenizer.from_pretrained(a.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    kw = dict(attn_implementation="sdpa", low_cpu_mem_usage=True)
    try:
        model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.float16, **kw)   # transformers>=5
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(a.base, torch_dtype=torch.float16, **kw)
    model.config.use_cache = False
    peft_cfg = LoraConfig(r=a.rank, lora_alpha=a.alpha, lora_dropout=0.05, target_modules="all-linear", bias="none", task_type="CAUSAL_LM")
    common = dict(output_dir=os.path.join(a.out, "trainer"), per_device_train_batch_size=a.batch, gradient_accumulation_steps=a.accum, num_train_epochs=a.epochs,
                  learning_rate=a.lr, lr_scheduler_type="cosine", warmup_ratio=0.1, logging_steps=5, save_strategy="no", report_to=[],
                  fp16=True, bf16=False, gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
                  ddp_find_unused_parameters=False, max_length=a.max_length, seed=7, max_steps=a.max_steps or -1)
    class NanGuard(TrainerCallback):
        bad = False
        def on_log(self, args, state, control, logs=None, **kw):
            v = (logs or {}).get("loss")
            if v is not None and (v != v or v in (float("inf"), float("-inf"))):
                NanGuard.bad = True
                control.should_training_stop = True
    ds_tr = Dataset.from_list(train_rows)
    if a.mode == "kto":
        from trl import KTOConfig, KTOTrainer
        cfg = KTOConfig(beta=a.beta, desirable_weight=stats.get("desirable_weight", 1.0), undesirable_weight=stats.get("undesirable_weight", 1.0), loss_type="kto", **common)
        tr = KTOTrainer(model=model, args=cfg, train_dataset=ds_tr, processing_class=tok, peft_config=peft_cfg, callbacks=[NanGuard()])
    else:
        from trl import SFTConfig, SFTTrainer
        cfg = SFTConfig(**common)
        tr = SFTTrainer(model=model, args=cfg, train_dataset=ds_tr.remove_columns(["label"]), processing_class=tok, peft_config=peft_cfg, callbacks=[NanGuard()])
    t0 = time.time()
    res = tr.train()
    losses = [h["loss"] for h in tr.state.log_history if "loss" in h]
    if NanGuard.bad or not losses:
        raise RuntimeError("loss стал NaN/inf — fp16-переполнение; адаптер не сохранён (снизьте lr или попробуйте другую базу)")
    if tr.is_world_process_zero():
        tr.model.save_pretrained(os.path.join(a.out, "peft"))
        tok.save_pretrained(os.path.join(a.out, "peft"))
    peak = [round(torch.cuda.max_memory_allocated(i) / 2**30, 2) for i in range(torch.cuda.device_count())]
    return {"ok": True, "steps": tr.state.global_step, "loss_first": losses[0], "loss_last": losses[-1], "seconds": int(time.time() - t0), "peak_gib": peak,
            "train_loss": float(res.training_loss)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="Qwen/Qwen3-8B"); ap.add_argument("--data", required=True, help="каталог из build_kto.py")
    ap.add_argument("--out", required=True); ap.add_argument("--mode", choices=["kto", "sft"], default="kto"); ap.add_argument("--gpus", default="0,1")
    ap.add_argument("--epochs", type=float, default=1.0); ap.add_argument("--lr", type=float, default=1e-5); ap.add_argument("--beta", type=float, default=0.1)
    ap.add_argument("--rank", type=int, default=16); ap.add_argument("--alpha", type=int, default=32); ap.add_argument("--batch", type=int, default=4); ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--max-length", type=int, default=1024); ap.add_argument("--max-steps", type=int, default=0); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.mode == "kto" and a.batch < 2:
        print("KTO с KL-оценкой требует batch>1", file=sys.stderr); return 2
    stats = json.load(open(os.path.join(a.data, "stats.json"), encoding="utf-8"))
    tr_rows = load_rows(os.path.join(a.data, "kto_train.jsonl"), a.mode)
    ev_rows = load_rows(os.path.join(a.data, "kto_eval.jsonl"), a.mode) if os.path.exists(os.path.join(a.data, "kto_eval.jsonl")) and os.path.getsize(os.path.join(a.data, "kto_eval.jsonl")) else []
    p = plan(a, stats)
    p["rows"] = {"train": len(tr_rows), "pos": sum(r["label"] for r in tr_rows), "neg": sum(not r["label"] for r in tr_rows)}
    if a.dry_run:
        print(json.dumps({"dry_run": True, "plan": p}, ensure_ascii=False)); return 0
    os.makedirs(a.out, exist_ok=True)
    try:
        r = train(a, tr_rows, ev_rows, stats)
    except Exception as e:
        r = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    r["plan"] = p
    if int(os.environ.get("LOCAL_RANK", "0")) == 0:
        json.dump(r, open(os.path.join(a.out, "train_result.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps(r, ensure_ascii=False))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
