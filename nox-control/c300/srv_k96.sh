echo "C300: srv_k96"
cd /workspace/nox
ls STOP 2>&1 | head -1; ls state/core/disk_low.flag 2>&1 | head -1; df -h /workspace | tail -1
tail -n 4 agent/out/autotrain.log | cut -c1-200
pgrep -fa "distill_v2.py train" | cut -c1-80
ls -la --time-style=+%T /tmp/bench_prev*.png 2>&1 | head -3
