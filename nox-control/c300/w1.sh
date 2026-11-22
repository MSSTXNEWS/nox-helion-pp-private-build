#!/bin/bash
for p in 8091 8082 8083 8081; do echo "$p $(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:$p/web/chat.html)"; done; pgrep -af web_server.py | cut -c1-80; tail -3 /root/nox/logs/web_server.log | cut -c1-150
