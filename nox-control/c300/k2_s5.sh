echo "C300: k2_s5"
ST=/workspace/nox/state
tail -4 $ST/k2_job2.log | cut -c1-250; cat $ST/k2_r8105.log | cut -c1-220; uptime; nvidia-smi --query-gpu=memory.used --format=csv,noheader; df -BG /workspace | tail -1
