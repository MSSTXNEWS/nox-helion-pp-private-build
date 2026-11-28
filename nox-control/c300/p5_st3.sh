echo "K1: p5_st3"; N=/workspace/nox
date -u +%T; echo "health=$(curl -s -m3 localhost:8104/health) ncmoe=$(ps -eo args | grep 'llama-server.*--port 8104' | grep -v grep | grep -o 'n-cpu-moe [0-9]*' | head -1) vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
tail -3 $N/state/body_restart.log | cut -c1-260
echo "--- body_ttft_upgrade.sh"; sed -n 1,70p $N/ops/body_ttft_upgrade.sh | cut -c1-240
echo "--- liska_donor2.sh"; grep -n -E "ncmoe|n-cpu-moe|body_restart|VRAM|sleep|train" $N/ops/liska_donor2.sh | head -30 | cut -c1-240
echo END
