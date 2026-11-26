echo "C300: srv_k17"
cd /workspace/nox
date -u +%T; tail -n 8 agent/out/autotrain.log | cut -c1-250
ls -t agent/autotrain/rounds | head -2
tail -n 3 state/p3/axis_rollback.jsonl | cut -c1-300
cat state/speed.json | grep -o '"moe_[a-z_]*": *[^,]*'
nvidia-smi --query-gpu=memory.used --format=csv,noheader
