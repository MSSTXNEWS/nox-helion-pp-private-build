echo "C300: ac_dedup2"
D=/workspace/nox/tmp/dd; V=/workspace/nox/venv/bin/python
$V -m pip install -q --no-deps --target $D scipy 2>&1 | tail -1; du -sh $D
ls -la --time-style=+%F /workspace/nox/ops/v5_knowledge_gpu_20261125 | head -15 | cut -c1-140
grep -an "knowledge" /workspace/nox/agent/autotrain/rounds/r038/train.log | head -3 | cut -c1-200
ls /workspace/nox/ops/v5_ready_205_20261125 | head; 
