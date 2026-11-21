#!/bin/bash
# READ-ONLY recon S1 (T1.1) + HF file list for GLM-5.3 UD-Q4_K_XL
echo "== mem"; cat /sys/fs/cgroup/memory.max 2>/dev/null; free -g | head -2; df -h /dev/shm / | cat
echo "== cpu"; nproc; lscpu | grep -E "Model name|Thread|Core|Socket|NUMA node\(s\)"
echo "== gpu"; nvidia-smi --query-gpu=name,memory.total,driver_version,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader
echo "== tools"; for t in python3 pip3 aria2c hf huggingface-cli cmake gcc g++ git nvcc curl; do printf "%s=%s " $t "$(command -v $t || echo -)"; done; echo
echo "== hf api"
curl -fsS "https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF/tree/main/UD-Q4_K_XL" | python3 -c "
import sys,json
d=json.load(sys.stdin); t=0
for f in d:
    print(f['path'],round(f.get('size',0)/2**30,1)); t+=f.get('size',0)
print('TOTAL GiB',round(t/2**30,1))" 2>&1 | head -20
