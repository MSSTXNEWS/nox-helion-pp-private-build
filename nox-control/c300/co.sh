#!/bin/bash
for p in 8090 8084 8095 8100 8096 8101 8098 8102; do pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$pid" ] && echo "$p: $(tr '\0' ' ' </proc/$pid/cmdline | cut -c1-170) (cwd $(readlink /proc/$pid/cwd))" || echo "$p: -"; done
cat /workspace/nox/integration/web_core.env 2>/dev/null | cut -c1-160
for u in /health /v1/health /v1/models /v1/core/health /api/health /memory/health /v1/memory/health; do echo "8090$u $(curl -s -m4 127.0.0.1:8090$u | head -c 160 | tr '\n' ' ')"; done
ls -t /workspace/nox/agent/out | head -8 | tr '\n' ' '
