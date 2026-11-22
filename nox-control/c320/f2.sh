#!/bin/bash
ps -eo pid,ni,pcpu,nlwp,etime,args --sort=-pcpu | head -12 | cut -c1-200
echo ---; cat /sys/fs/cgroup/cpu.stat | grep -E 'throttled|nr_periods'; sleep 5; cat /sys/fs/cgroup/cpu.stat | grep -E 'throttled_usec|nr_throttled|nr_periods'
echo ---; B=/root/nox/llama.cpp-f/build/bin/llama-server; $B --help 2>&1 | grep -iE -A2 'spec-type|spec-draft-n|ngram|mtp|--n-cpu-moe|cache-reuse|slot-prompt-sim|--cache-type-k|--swa' | cut -c1-220 | head -50
echo ---; cd /root/nox/llama.cpp-f; grep -rn "nextn\|NEXTN" src/models/glm*.cpp src/llama-model.cpp 2>/dev/null | head -8; grep -rln "mtp" src common tools/server 2>/dev/null | head
echo ---; python3 - <<'PY' 2>&1 | tail -8
import sys,glob
sys.path.insert(0,'/root/nox/llama.cpp-f/gguf-py'); from gguf import GGUFReader
for f in sorted(glob.glob('/dev/shm/glm53f/*.gguf')):
    r=GGUFReader(f)
    n=[t.name+str(list(t.shape))+t.tensor_type.name for t in r.tensors if t.name.startswith('blk.45') or 'nextn' in t.name]
    if n: print(f[-18:],len(n),n[:6])
PY
echo ---; grep -E "buffer size|KV|offloaded|n_ctx|model size|spec|nextn" /root/nox/logs/glm_8081.log | head -14 | cut -c1-200
