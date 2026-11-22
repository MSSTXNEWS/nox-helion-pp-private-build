#!/bin/bash
grep -a -E "model buffer|KV buffer|compute buffer|n_layer|n_ctx|offload|free|alloc|n_expert|n_embd |arch" /root/nox/logs/glm_8081.log | cut -c1-200 | head -30
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
