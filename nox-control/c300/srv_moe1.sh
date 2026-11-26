#!/bin/bash
L=/workspace/nox/agent/autotrain/rounds/r032/train.log
grep -a -i -E "moe|grouped|backend|triton|autotune" $L | head -12 | cut -c1-220
tr '\0' '\n' </proc/$(pgrep -f "distill_v2.py train" | head -1)/environ | grep -E "UNSLOTH|TORCH|PYTORCH|CUDA" | sed -E 's/(KEY|TOKEN)=.*/\1=***/'
grep -n -i -E "UNSLOTH_MOE|moe_backend|grouped_mm" /workspace/nox/distill_v2/code/distill_v2.py /workspace/nox/agent/autotrain/autotrain.sh | head -5 | cut -c1-200
grep -n -i "def select_moe_backend\|UNSLOTH_MOE_BACKEND\|_grouped_mm\|torch.cuda.get_device_capability" /workspace/nox/distill_v2/code/unsloth_compiled_cache/moe_utils.py | head -12 | cut -c1-200
/workspace/nox/venv/bin/python -c "import torch;print(torch.__version__, hasattr(torch,'_grouped_mm'), torch.cuda.get_device_capability())" 2>&1 | tail -1
