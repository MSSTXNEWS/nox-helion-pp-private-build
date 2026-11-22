#!/bin/bash
echo "== модели"; ps -eo pid,etimes,pcpu,args | grep "llama-server" | grep -v grep | sed -E 's/ -(c|b|ub|fa|np|t|tb|amb) .*//' | cut -c1-230
for p in 8081 8083 18098 8082; do echo "$p $(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/health)"; done
tr '\0' '\n' < /proc/$(pgrep -f "python3 .*gateway.py" | head -1)/environ | grep -E "NOX_UPSTREAM|NOX_FAST_UPSTREAM|NOX_MODEL"
