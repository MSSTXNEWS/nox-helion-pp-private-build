#!/bin/bash
head -c 3000 /workspace/nox/agent/out/SERVE_STATUS.md; echo; echo ====
curl -s -m4 127.0.0.1:8090/health | python3 -c "import json,sys; d=json.load(sys.stdin); print({k:(v if not isinstance(v,dict) else {kk:str(vv)[:40] for kk,vv in list(v.items())[:6]}) for k,v in d.items()})" | cut -c1-1500
grep -oE '"/v1/[a-z_/]+"|p == "[^"]+"|startswith\("[^"]+"' /workspace/nox/brain/BRAIN/nox_core.py | sort -u | head -40 | tr '\n' ' '
