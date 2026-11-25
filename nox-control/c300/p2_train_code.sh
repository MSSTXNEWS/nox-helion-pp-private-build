#!/bin/bash
# P2 read-only: distill_v2 code config grep (bounded)
D=/workspace/nox/distill_v2/code; ls -la $D | head -40
for f in $(ls $D/*.py | head -12); do echo "=== $f $(wc -l <$f)"; done
f=$D/distill_v2.py; [ -f $f ] || f=$(ls $D/*.py | head -1)
echo "=== GREP $f"
grep -nE 'add_argument|dtype|float16|bfloat16|autocast|GradScaler|attn_implementation|sdpa|gradient_checkpoint|use_reentrant|AdamW|optim|micro|accum|max.len|num_workers|pin_memory|torch.compile|LoraConfig|lora_r|r=[0-9]|target_modules|load_in|BitsAndBytes|packing|bucket|sort|eval_every|ckpt.every|save_pretrained|empty_cache|expandable|PYTORCH_CUDA' $D/*.py 2>/dev/null | cut -c1-210 | head -150
echo "=== autotrain train cmdline"; grep -nE 'distill_v2.py train|PYTORCH|CUDA_|--max-len|--bs|--accum' /workspace/nox/agent/autotrain/autotrain.sh | cut -c1-260 | head -20
echo "=== env of trainer"; tr '\0' '\n' </proc/1984162/environ 2>/dev/null | grep -E '^(PYTORCH|CUDA|TORCH|OMP|MKL|UNSLOTH|TOKENIZERS|HF_)' | cut -c1-120
echo "=== threads/cpu of trainer"; ps -L -p 1984162 -o pid,psr,pcpu --no-headers 2>/dev/null | sort -k3 -nr | head -6; grep -E 'Cpus_allowed_list|Threads' /proc/1984162/status
echo "=== DONE"
