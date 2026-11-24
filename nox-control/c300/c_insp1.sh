#!/bin/bash
# c_insp1: read-only inventory of S1 web server (no changes)
echo "== DISK"; df -h / | tail -1
echo "== SERVER DIR"; ls -la /workspace/nox/web/pkg/server/ 2>&1 | head -40
echo "== ROUTES"; grep -n 'p == \|startswith' /workspace/nox/web/pkg/server/web_server.py 2>&1 | head -120
echo "== RUN_WEB"; sed -n 1,60p /workspace/nox/web/pkg/server/run_web.sh 2>&1
echo "== HEALTH"; curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/api/chat/health
echo "== QA DIR"; ls /workspace/nox/web/site/qa 2>&1 | head -30; ls -la /workspace/nox/qa_audit.py /workspace/nox/qa_ctl.py 2>&1
echo "== OPS"; ls /workspace/nox/ops/controller 2>&1 | head -30
echo "== STATE"; ls -la /workspace/nox/state 2>&1 | head -30
