#!/bin/bash
S=/workspace/nox/web/pkg/server; cat $S/run_web.sh | head -40 | cut -c1-200; echo ===; head -20 $S/web_watchdog.sh | cut -c1-200
echo ===; cat $S/web_server.pid; ps -p $(cat $S/web_server.pid) -o args= 2>&1 | cut -c1-120
ls -t /workspace/nox/web/pkg/server/*.log /workspace/nox/logs/*web* 2>/dev/null | head -3; f=$(ls -t /workspace/nox/logs/*web*.log 2>/dev/null | head -1); [ -n "$f" ] && tail -8 $f | cut -c1-200
grep -n "os.environ.get(\"NOX_" $S/web_server.py $S/chat_core.py | cut -c1-170 | head -30
