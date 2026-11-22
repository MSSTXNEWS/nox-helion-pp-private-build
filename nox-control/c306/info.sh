#!/bin/bash
date -u +%T; tail -n 2 /root/nox/logs/flash.log | cut -c1-120; pgrep -fa "python3 flash.py|port 8081" | cut -c1-80
grep -E "model buffer|KV buffer|n_ctx|n_layer|n_expert|arch|n_embd |compute buffer|offload|MiB free|n_ctx_seq|kv_lora|n_head_kv" /root/nox/logs/glm_8081.log | cut -c1-210 | head -25
grep -n "taskset\|nice" /root/nox/flash.py | cut -c1-100 | head -3
nproc; lscpu | grep -E "^CPU\(s\)|Thread|Socket|Core" | head
