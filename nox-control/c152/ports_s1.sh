#!/bin/bash
uptime; for p in 8091 8082 8081 8083 8093 8094 8095; do echo "$p $(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/health 2>&1)"; done
curl -s -m 5 -o /dev/null -w "web chat=%{http_code}\n" http://127.0.0.1:8091/web/chat.html
ps -eo pid,etimes,pcpu,args | grep -E "llama-server|gateway|web_server|tts_server|stt_server" | grep -v grep | sed -E 's/ -(c|b|ub|fa|np|t|tb|amb) .*//' | cut -c1-200
tail -5 /root/nox/logs/web_server.log | cut -c1-200; tail -5 /root/nox/logs/gateway.log 2>/dev/null | cut -c1-200
free -g | sed -n 2p; df -h / | tail -1
