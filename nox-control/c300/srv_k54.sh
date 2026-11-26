echo "C300: srv_k54"
date -u +%T; grep -a "chain\|rc=\|Error\|Traceback\|error" /workspace/nox/ops/dpo/run.log | tail -n 12 | cut -c1-300
tail -c 1500 /workspace/nox/ops/dpo/run.log | tr '\r' '\n' | tail -n 6 | cut -c1-250
nvidia-smi --query-gpu=memory.used --format=csv,noheader
