echo "C300: srv_k82"
P=/workspace/nox/ops/v5_knowledge_gpu_20261125/phase.py; ls -la $P | cut -c1-120
grep -n "def select" -A40 $P | cut -c1-200 | head -60
grep -n "select" $P | head -8 | cut -c1-160
ls /workspace/nox/state/core/disk_low.flag 2>&1 | head -1
