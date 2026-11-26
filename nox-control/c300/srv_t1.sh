#!/bin/bash
L=$(ls -td /workspace/nox/agent/autotrain/rounds/r0*/ | head -1)train.log; echo $L
head -60 $L | cut -c1-230 | grep -v "^$" | head -45
echo ==== steps; grep -a "шаг" $L | tail -8 | cut -c1-260
grep -a -i -E "liger|xformers|sdpa|flash|compile|packing|pack|speed|tok/s|ток/с|с/шаг|s/it" $L | head -12 | cut -c1-230
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,clocks.sm,clocks.max.sm,power.draw,temperature.gpu --format=csv
python3 -c "import flash_attn" 2>&1 | tail -1; /workspace/nox/venv/bin/python -c "import liger_kernel;print('liger',liger_kernel.__version__)" 2>&1 | tail -1
cat /workspace/nox/state/speed.json 2>/dev/null | head -c 600
