#!/bin/bash
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/bridge
curl -fsSL $B/nox_bridge.py -o /opt/nox-bridge/nox_bridge.py && supervisorctl restart nox-bridge >/dev/null 2>&1
sleep 6; curl -s -m 5 http://127.0.0.1:8091/health; echo
curl -fsSL $B/chat_test.py -o /opt/chat_test.py
nohup /root/nox/venv/bin/python /opt/chat_test.py </dev/null >/opt/chat_test.out 2>&1 &
echo started
