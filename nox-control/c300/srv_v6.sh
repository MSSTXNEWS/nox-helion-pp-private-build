#!/bin/bash
F=/workspace/nox/judges/judge_service.py
sed -n 315,326p $F | cut -c1-200; sed -n 340,420p $F | cut -c1-250
cat /workspace/nox/state/gpu_phase 2>/dev/null | head -2; ls /workspace/nox/state/judges_gpu_offload.off 2>&1 | tail -1
curl -s -m4 127.0.0.1:8300/judges | python3 -c "
import sys,json
d=json.load(sys.stdin); d=d.get('judges',d)
for k,v in (d.items() if isinstance(d,dict) else []): print(k.split('/')[-1][:40], v.get('device'), v.get('status'), v.get('kind'), v.get('deep'))" | head -30
