#!/bin/bash
# c_diag3: read-only поиск процесса recall_api :8095, маршрута /memory/api и страниц diary/automations
S=/workspace/nox/web/pkg/server; W=/workspace/nox/web/site
echo "LISTEN 8095:"; (ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep 8095
PID=$(ss -ltnp 2>/dev/null | grep ':8095 ' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1)
[ -n "$PID" ] && { echo "PID $PID"; tr '\0' ' ' < /proc/$PID/cmdline; echo; readlink /proc/$PID/cwd; }
echo "MEMORY ROUTE:"; grep -n 'memory/api\|_memory(\|def _memory' $S/*.py | cut -c1-200 | head -20
echo "PAGES:"; ls -la $W/diary.html $W/automations.html 2>&1
echo "RECALL HEALTH:"; curl -s -m 5 -w ' [%{http_code}]' http://127.0.0.1:8095/health; echo
echo "MEMORY PROXY TEST:"; curl -s -m 8 -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8091/memory/api/recall?q=test'
