#!/bin/bash
# c_diag4: read-only разбор /memory/api и поиск процесса recall
S=/workspace/nox/web/pkg/server
echo "MEMORY FN:"; sed -n '285,300p' $S/web_server.py | cut -c1-300
echo "MEM PATHS:"; grep -n 'MEM_PATHS\|RECALL\|8095' $S/web_server.py | cut -c1-200 | head -8
echo "RECALL PROCS:"; pgrep -af 'recall' | cut -c1-200 | head -5
echo "GET /memory/api:"; curl -s -m 8 -w ' [%{http_code}]' 'http://127.0.0.1:8091/memory/api' | head -c 300; echo
echo "POST /memory/api:"; curl -s -m 8 -w ' [%{http_code}]' -X POST http://127.0.0.1:8091/memory/api -H 'Content-Type: application/json' -d '{"q":"test"}' | head -c 300; echo
echo "CMD LOG tail:"; tail -n 2 /workspace/nox/state/cmd_log.jsonl
