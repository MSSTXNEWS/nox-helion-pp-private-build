#!/bin/bash
# P2 read-only diagnosis of port 8091 (web_server.py)
date -u
echo "## LISTEN 8091/18091"; ss -ltnpH | grep -E ':(8091|18091|8090) ' | cut -c1-160
echo "## web_server procs"; ps -eo pid,ppid,etimes,pcpu,rss,args | grep -Ei 'web_server|run_web|run_server' | grep -v grep | cut -c1-220
echo "## locate"; find /workspace/nox -maxdepth 4 \( -name 'web_server.py*' -o -name 'run_web.sh' \) -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort | tail -25
WS=$(find /workspace/nox -maxdepth 4 -name web_server.py 2>/dev/null | head -1); echo "WS=$WS"
echo "## syntax check"; [ -n "$WS" ] && /workspace/nox/venv/bin/python -m py_compile "$WS" 2>&1 | tail -5 && echo "py_compile rc=$?"
echo "## .bak_n_ws"; ls -la $(dirname "$WS")/web_server.py.bak_n_ws* 2>/dev/null
echo "## run_web.sh"; sed -n 1,60p /workspace/nox/web/pkg/server/run_web.sh 2>/dev/null | cut -c1-200
echo "## logs"; for f in /workspace/nox/agent/out/web_boot.log /workspace/nox/web/pkg/server/*.log /workspace/nox/web/*.log /workspace/nox/agent/out/web*.log; do [ -f "$f" ] && { echo "--- $f ($(stat -c %y $f))"; tail -25 "$f" | cut -c1-220; }; done
echo "## start_extra mentions web"; grep -nE '8091|web_server|run_web' /workspace/nox/svc/start_extra.sh /workspace/nox/svc/start_all.sh /workspace/nox/serve/*.sh 2>/dev/null | cut -c1-200 | head
echo "## supervisor"; supervisorctl status 2>&1 | grep -Ei 'web|chat'
echo "## curl"; for u in http://127.0.0.1:8091/chat.html http://127.0.0.1:8091/api/chat http://127.0.0.1:18091/chat.html; do echo "$u -> $(curl -s -o /dev/null -m 5 -w '%{http_code}' $u)"; done
echo "## mtime vs death"; stat -c '%y %n' $WS 2>/dev/null
echo "## DONE"
