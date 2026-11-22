#!/bin/bash
tail -c 2200 /root/nox/logs/V7-04.run.log | tr -cd '\11\12\15\40-\176\200-\377' | cut -c1-300
echo; cat /root/nox/state/v7_flags.json | tr -d '\n'; echo
for p in 8081 8082 8083 8084 8090 8091; do printf "$p:%s " $(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:$p/health); done; echo
