#!/bin/bash
cd /root/nox
echo "== v7 state/receipts"; ls -t /root/nox/state 2>/dev/null| head; find /root/nox -maxdepth 3 \( -iname "*receipt*" -o -iname "V7-*" \) -mmin -900 2>/dev/null | head -20
ls /root/nox/backups/v7/; tail -n 30 /root/nox/logs/V7-04.run.log | cut -c1-180
echo "== accept"; ls /root/nox/src/wow7/deploy; tail -n 20 /root/nox/logs/V7-04.test_brain.log | cut -c1-160
echo "== web_server.py head"; grep -n "^def \|^class \|^import\|^from\|8082\|8090\|8091\|/api/" web_server.py | cut -c1-150 | head -80
echo "== wow7 pkg"; ls src/wow7/brain src/wow7/common src/wow7/prime src/wow7/act repo/nox-control/wow7 2>&1 | head -60
echo "== core health"; curl -s -m5 http://127.0.0.1:8090/health | head -c 400; echo; tail -n 5 logs/core.log | cut -c1-200
echo "== web log"; tail -n 8 logs/web_server.log | cut -c1-160
