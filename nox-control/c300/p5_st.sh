echo "K1: p5_st"; N=/workspace/nox
ps -eo pid,etimes,args | grep -E "llama-server.*8104|dpo|train|gpu_phase" | grep -v grep | sed -E 's#(/[A-Za-z0-9_.-]+)+/#<d>/#g' | cut -c1-260
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo "health=$(curl -s -m3 localhost:8104/health)"; tail -4 $N/state/body_restart.log | cut -c1-220
ls -la --time-style=+%H:%M $N/state/ | grep -E "gpu_phase|gen_hold|train" | awk '{print $6,$7}'
echo END
