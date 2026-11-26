echo "C300: srv_k44"
cd /workspace/nox/ops/dpo
date -u +%T; pgrep -f chain_dry | head -1; pgrep -fa "distill_v2.py|ckpt_guard" | cut -c1-80 | head -3
tail -n 25 run.log | cut -c1-250
nvidia-smi --query-gpu=memory.used --format=csv,noheader
