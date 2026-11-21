#!/bin/bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
pgrep -af llama-server | cut -c1-170
echo "== glm errors"; grep -E " E |error|failed|CUDA|out of memory|cudaMalloc|alloc" /root/nox/logs/glm_server.log | grep -v "unused tensor" | head -8 | cut -c1-220
