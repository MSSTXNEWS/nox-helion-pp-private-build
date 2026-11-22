#!/bin/bash
echo "health body: $(curl -s -m5 http://127.0.0.1:8082/health | head -c 300)"
echo "glm body: $(curl -s -m5 http://127.0.0.1:8081/health | head -c 100)"
ps -eo pid,etimes,args | grep -E "gateway.py" | grep -v grep | cut -c1-100
grep -n "prime\|Error\|error" /root/nox/logs/gateway.log | grep -v BrokenPipe | tail -12 | cut -c1-230
grep -n "def do_GET" -A12 /root/nox/repo/nox-control/glm53/gateway.py | grep -n health -A4 | head -12
