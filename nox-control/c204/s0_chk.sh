#!/bin/bash
for p in 8081 8082 8083 8091 8095; do printf "$p:%s " $(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:$p/health); done; echo
ps -eo pid,etimes,args | grep -E "gateway.py|web_server" | grep -v grep | cut -c1-120
GP=$(pgrep -f glm53/gateway.py|head -1); tr '\0' '\n' </proc/$GP/environ | grep -E "^NOX_|PYTHONPATH" | tr '\n' ' '; echo
cat /root/nox/state/v7_flags.json 2>&1 | head -5
ls /root/nox/repo/nox-control/wow7 2>&1 | head -3; ls /root/nox/repo/nox-control/glm53 | tr '\n' ' '
cat /root/nox/receipts/V7-00.json | head -c 600
