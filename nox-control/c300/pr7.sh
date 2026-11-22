#!/bin/bash
L=/root/nox/logs/restart_8082.log; n=$(wc -l < $L)
python3 /root/nox/restart_same.py 8082 | tail -1; sleep 6
curl -s -m60 127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Привет"}],"mode":"fast","stream":false}' | head -c 200; echo
sleep 2; tail -n +$((n+1)) $L | grep -iE "prime|Traceback|Error" | head -10 | cut -c1-160
