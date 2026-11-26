echo "C300: srv_k108"
cd /workspace/nox; date -u +%T; ls -la STOP; cat ops/dpo/run5.log 2>&1 | tail -12 | cut -c1-200
pgrep -fa "chain5|teacher_dump|quant4|distill_v2|ckpt_guard|llama-server" | cut -c1-120
uptime; df -h /workspace|tail -1; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
