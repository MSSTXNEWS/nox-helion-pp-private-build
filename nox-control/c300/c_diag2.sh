#!/bin/bash
# c_diag2: read-only diagnosis of /api/cmd self-call (no changes)
S=/workspace/nox/web/pkg/server
echo "HEALTH $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/api/chat/health)"
echo "SERVER CLASS:"; grep -n 'ThreadingHTTPServer\|HTTPServer(' $S/web_server.py | head -5
echo "LAST LOG:"; tail -n 12 /workspace/nox/agent/out/web_server.log 2>/dev/null | cut -c1-220
echo "CMD LOG:"; tail -n 5 /workspace/nox/state/cmd_log.jsonl
echo "PROC:"; pgrep -af web_server.py | head -3
echo "TEST POST /api/cmd health:"; curl -s -m 15 -w ' [%{http_code}]' -X POST http://127.0.0.1:8091/api/cmd -H 'Content-Type: application/json' -d '{"name":"health"}' | head -c 300; echo
echo "TEST GET /svc/_status:"; curl -s -m 10 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/svc/_status
