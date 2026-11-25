#!/bin/bash
# P2 read-only training audit (no secrets printed)
echo "## PROCS"; ps -eo pid,etimes,pcpu,rss,args | grep -E 'distill|train|lora|unsloth|peft' | grep -v -E 'grep|compile_worker' | cut -c1-260
echo "## VERSIONS"; /workspace/nox/venv/bin/python - <<'PY' 2>&1
import importlib
for m in ["torch","transformers","peft","unsloth","xformers","liger_kernel","bitsandbytes","trl","accelerate","flash_attn","datasets"]:
    try:
        mod=importlib.import_module(m); print(m, getattr(mod,"__version__","?"))
    except Exception as e: print(m,"MISSING")
import torch; print("cuda",torch.version.cuda, torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None)
PY
echo "## FILES"; ls -la /workspace/nox/distill_v2/ 2>/dev/null | head -40; ls /workspace/nox/agent/autotrain/ 2>/dev/null | head
echo "## AUTOTRAIN.SH"; sed -n 1,80p /workspace/nox/agent/autotrain/autotrain.sh 2>/dev/null | cut -c1-200
f=$(ls /workspace/nox/distill_v2.py /workspace/nox/distill_v2/distill_v2.py 2>/dev/null | head -1); echo "## DISTILL_V2 $f"; wc -l "$f"
grep -nE 'add_argument|dtype|fp16|bf16|autocast|GradScaler|attn_implementation|sdpa|gradient_checkpoint|AdamW|optim|batch|accum|max_len|seq|num_workers|pin_memory|compile|LoraConfig|rank|target_modules|save|eval|load_in|quant|packing|logit|teacher' "$f" 2>/dev/null | cut -c1-200 | head -120
echo "## LOG TAIL"; tail -30 /workspace/nox/agent/autotrain/rounds/r028/train.log 2>/dev/null | cut -c1-220
echo "## DMON 30s"; timeout 40 nvidia-smi dmon -c 30 -s um 2>&1 | head -40
echo "## CKPT"; ls -la /workspace/nox/distill_v2/ckpt 2>/dev/null | tail -8; du -sh /workspace/nox/distill_v2/* 2>/dev/null
echo "## DONE"
