echo "C300: ac_mb2"
F=/workspace/nox/distill_v2/code/distill_v2.py
grep -nE "batch|BATCH|grad_acc|toks_per|tok_budget|pad_to|per_step" $F | grep -v "^.*#.*test" | head -50 | cut -c1-200
grep -aE "bs=|batch|микро|токенов в шаге|tok/step|ступень" /workspace/nox/agent/autotrain/rounds/r038/train.log | head -6 | cut -c1-200
nvidia-smi --query-gpu=memory.used --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | sort -t, -k2 -rn | head -2
