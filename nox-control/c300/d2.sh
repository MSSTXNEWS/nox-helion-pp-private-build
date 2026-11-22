#!/bin/bash
P=$(pgrep -f 'llama.cpp-f.*8081'|head -1); echo pid=$P; tr '\0' ' ' </proc/$P/cmdline | cut -c60-420; echo
lscpu | grep -E "NUMA node[0-9]"; which numactl numastat; cat /sys/fs/cgroup/cpuset.cpus.effective 2>/dev/null
python3 - <<P
import re,collections
c=collections.Counter()
for l in open("/proc/$P/numa_maps"):
    if "glm53f" in l:
        for k,v in re.findall(r"N(\d+)=(\d+)",l): c[k]+=int(v)
print("GLM shm pages by node (GB):",{k:round(v*4096/2**30,1) for k,v in c.items()})
P
grep -iE "mtp|nextn" /root/nox/logs/glm_8081.log | head -4 | cut -c1-160
/root/nox/llama.cpp-f/build/bin/llama-server --help 2>&1 | grep -iE "^ *--numa|cpu-moe|cache-reuse|spec-draft-n-max" | cut -c1-120
cat /proc/loadavg
