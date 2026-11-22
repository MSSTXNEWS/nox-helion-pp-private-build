#!/bin/bash
sed -n 72,82p /root/nox/web_server.py | cut -c1-260
echo ====; sed -n 90,104p /root/nox/web_server.py | cut -c1-200
echo ===; ls /root/nox/repo/nox-control/qs6/recall_api.py; cd /root/nox/repo && git log --oneline -1 2>&1 | head -1
pid=$(ss -ltnp | grep ":8095 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "cwd $(readlink /proc/$pid/cwd)"; tr '\0' '\n' </proc/$pid/environ | grep -i "^NOX\|PYTHONPATH" | cut -c1-120
pid=$(ss -ltnp | grep ":8091 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "web cwd $(readlink /proc/$pid/cwd)"; tr '\0' '\n' </proc/$pid/environ | grep -i "^NOX\|PORT" | cut -c1-120
curl -s -m3 http://127.0.0.1:8091/memory/health | head -c 300
