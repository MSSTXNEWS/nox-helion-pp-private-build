#!/bin/bash
python3 - <<'PY'
import json
d=json.load(open('/root/nox/logs/recon_B.txt')) if False else None
PY
sed -n '/"gpu"/,$p' /root/nox/logs/recon_B.txt | sed -n '18,80p' | cut -c1-200
echo ---; cat /sys/fs/cgroup/cpu.stat 2>/dev/null | head -6
for b in /root/nox/ik_llama/build/bin/llama-server; do $b --help 2>&1 | grep -iE 'spec-type|draft-mtp|dflash|op-offload|cache-reuse|slot-save|numa|moe-cache|-ub' | cut -c1-150 | head -14; done
