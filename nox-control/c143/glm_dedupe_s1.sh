#!/bin/bash
echo "== procs"; ps -eo pid,ppid,etimes,pcpu,args | grep -E "llama-server -m /root/nox/glm53|glm.*(watch|loop|start)|run_glm|keep" | grep -v grep | cut -c1-260
OLD=$(pgrep -f "llama-server -m /root/nox/glm53" | xargs -r ps -o pid=,etimes= -p | sort -k2 -nr | head -1 | awk '{print $1}')
for p in $(pgrep -f "llama-server -m /root/nox/glm53"); do [ "$p" != "$OLD" ] && { echo "kill dup $p"; kill $p; }; done
sleep 8; echo "keep $OLD"; pgrep -af "llama-server -m /root/nox/glm53" | cut -c1-80
echo "== glm test"; curl -s -m 100 http://127.0.0.1:18098/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Одним предложением по-русски: что такое Луна?"}],"max_tokens":50,"stream":false}' -w "\ntime=%{time_total}\n" | tail -c 700
uptime
