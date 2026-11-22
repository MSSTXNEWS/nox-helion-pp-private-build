#!/bin/bash
# c172: только проверка (ничего не меняет): ответы веб-сервера S1
for u in /api/health /api/pc-metrics /web/system.html /web/studio.html /web/nox-mini.js /memory/health /glm/v1/nox/stats; do echo "$u $(curl -s -m10 -o /tmp/c172.b -w '%{http_code}' http://127.0.0.1:8091$u) $(head -c 160 /tmp/c172.b | tr '\n' ' ')"; done
pgrep -af web_server | head -3; tail -5 /root/nox/logs/web_server.log
