#!/bin/bash
for p in 8081 8082 8083 8091 8093 8094; do echo "$p $(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/health) $(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/)"; done
pgrep -af "gateway.py|web_server|llama-server" | cut -c1-120; ls /root/nox/web 2>/dev/null | head -3; tail -4 /root/nox/logs/gateway.log | cut -c1-200; grep -vE "unused tensor" /root/nox/logs/glm_server.log | tail -4 | cut -c1-160; grep -E "ALL_OK|SOME_BAD" /root/nox/logs/redo.log; ls /dev/shm/nox_glm | wc -l
