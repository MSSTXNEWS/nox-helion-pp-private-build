echo "C300: srv_k77"
df -h /workspace | tail -1
D=/workspace/nox/ops/v5_live_adapter_20261125
ls -la --time-style=+%m-%d_%H:%M $D | cut -c1-200 | head -60
du -sh $D
ls -la /workspace/nox/ops/v5_knowledge_gpu_20261125/ | grep -i "bak_add_accepted_long" | cut -c1-200
