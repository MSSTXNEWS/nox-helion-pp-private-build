#!/bin/bash
grep -v '^#' /root/nox/start_glm.sh | head -25 | cut -c1-400
echo ---; ls -la /dev/shm/glm53f | awk '{print $5,$9}' | head; ls /root/nox/llama.cpp-f/build/bin | grep -E 'bench|gguf|perplexity|server' | tr '\n' ' '
echo ---; lscpu | grep -E 'Model name|^CPU\(s\)|Thread|NUMA node\(s\)|Flags' | cut -c1-90; lscpu | grep -o 'avx512[a-z_0-9]*\|amx[a-z_0-9]*\|avx_vnni' | sort -u | tr '\n' ' '
echo; cat /sys/fs/cgroup/cpu.max /sys/fs/cgroup/cpu.stat 2>/dev/null | head -8
echo ---; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo ---; python3 - <<'PY' 2>&1 | head -40
import sys
try:
    sys.path.insert(0,'/root/nox/llama.cpp-f/gguf-py'); from gguf import GGUFReader
    r=GGUFReader('/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf')
    for k,f in r.fields.items():
        if any(s in k for s in ['arch','block_count','nextn','expert','context_length','embedding_length','head_count','kv_lora','leading_dense','used_count']):
            try: print(k, f.contents())
            except Exception: print(k)
    n=[t.name for t in r.tensors if 'nextn' in t.name or '.eh_proj' in t.name]
    print('nextn tensors in shard1:',n[:5])
except Exception as e: print('ERR',e)
PY
grep -c . /dev/null; for f in /dev/shm/glm53f/*.gguf; do :; done; strings -n 8 /dev/shm/glm53f/*00006.gguf 2>/dev/null | grep -m3 nextn
