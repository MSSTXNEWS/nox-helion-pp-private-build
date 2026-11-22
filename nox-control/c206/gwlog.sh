#!/bin/bash
for p in 8081 8082 8083 8091; do printf "$p:%s " $(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:$p/health); done; echo
ps -eo pid,etimes,args | grep -E "gateway.py|gw_env" | grep -v grep | cut -c1-110
tail -n 25 /root/nox/logs/gateway.log | cut -c1-220
ls /root/nox/repo/nox-control/wow7/deploy 2>&1 | head -3
