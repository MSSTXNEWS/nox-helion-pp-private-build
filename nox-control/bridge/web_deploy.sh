#!/bin/bash
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/bridge
cd /opt/nox-bridge || exit 1
mkdir -p /opt/nox-bridge.bak && cp -a nox_bridge.py nox_soul.py /opt/nox-bridge.bak/ 2>/dev/null; cp -a nox_webapi.py /opt/nox-bridge.bak/ 2>/dev/null
for f in nox_bridge.py nox_soul.py nox_webapi.py; do curl -fsSL $B/$f -o /tmp/$f.new && python3 -m py_compile /tmp/$f.new && mv /tmp/$f.new /opt/nox-bridge/$f || { echo FAIL $f; exit 1; }; done
curl -fsSL $B/web_test.py -o /opt/web_test.py
supervisorctl restart nox-bridge >/dev/null 2>&1; sleep 8
supervisorctl status nox-bridge; curl -s -m5 127.0.0.1:8091/api/health; echo
tail -3 /root/nox/logs/nox_bridge.log | cut -c1-200
nohup /root/nox/venv/bin/python /opt/web_test.py </dev/null >/opt/web_test.out 2>&1 &
echo started
