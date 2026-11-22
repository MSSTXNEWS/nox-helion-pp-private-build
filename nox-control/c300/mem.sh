#!/bin/bash
hostname; lscpu | grep -E 'Model name|^Socket|NUMA node\(s\)'; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
dmidecode -t memory 2>/dev/null | grep -E '^\s+(Speed|Configured Memory Speed|Type):' | sort | uniq -c | head -6
free -g | sed -n 2p; cat /sys/fs/cgroup/cpu.max 2>/dev/null
python3 - <<'P'
import time
try:
    import numpy as np
    a=np.ones(512*1024*1024//8); b=np.empty_like(a)
    for _ in range(2): np.copyto(b,a)
    t=time.time(); n=5
    for _ in range(n): np.copyto(b,a)
    print("1-thread copy GB/s: %.1f" % (n*2*a.nbytes/(time.time()-t)/1e9))
except Exception as e: print("numpy fail", e)
P
