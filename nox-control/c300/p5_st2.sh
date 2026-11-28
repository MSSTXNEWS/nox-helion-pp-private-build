echo "K1: p5_st2"; N=/workspace/nox
date -u +%T; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | while IFS=, read p m; do echo "$p $m $(ps -o args= -p $p | sed -E 's#(/[A-Za-z0-9_.-]+)+/#<d>/#g' | cut -c1-110)"; done
ss -ltnp | grep -E ":(8104|8105) " | sed -E 's/users:.*pid=([0-9]+).*/pid=\1/'
echo "health=$(curl -s -m3 localhost:8104/health)"
ps -eo pid,etimes,args | grep -E "body_restart|donor|llama-server --host 127.0.0.1 --port 8104" | grep -v grep | cut -c1-200
ls -la --time-style=+%H:%M:%S $N/state/gen_hold $N/state/body_restart.lock $N/state/gpu_phase 2>&1 | awk '{print $6,$7}'
tail -5 $N/agent/out/donor_donor_hybrid.log 2>/dev/null | cut -c1-200
cat $N/state/train_vram_cap_mib; cat $N/state/gpu_phase 2>/dev/null | head -3
echo END
