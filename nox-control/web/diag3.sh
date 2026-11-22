#!/bin/bash
sed -n 206,232p /root/nox/web_server.py | cut -c1-250
echo "== worker"; grep -n "Errno\|status\"\] = \"error\|def _worker\|\"error\"\] =\|except Exception as e" /root/nox/web_server.py | head -12 | cut -c1-200
echo "== gw health"; curl -s -m5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/v1/models; grep -n "^GW\|^TAG" /root/nox/web_server.py
