#!/bin/bash
cat /workspace/nox/canon_night/run_embed.sh | cut -c1-200
grep -n "embed" /workspace/nox/stewards/chat_guard.py /workspace/nox/stewards/dispatcher_worm.py /workspace/nox/ops/p3_cpuset_guard.sh | cut -c1-200 | head -12
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
