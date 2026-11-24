#!/bin/bash
S=/workspace/nox/web/pkg/server; head -12 $S/run_web.sh | cut -c1-200; grep -n '^ *[a-z]*)' $S/run_web.sh | head
for p in 8090 8091 8084 8093 8094 8095 8100; do echo -n "$p=$(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:$p/) "; done; echo
tail -15 /workspace/nox/agent/out/web_server.log | cut -c1-200; echo ===; tail -5 /workspace/nox/agent/out/web_watchdog.log 2>/dev/null
cat /workspace/nox/web/pkg/server/../deploy/*.env $S/web_core.env 2>/dev/null | head; ls /workspace/nox/run 2>/dev/null | head -20 | tr '\n' ' '
