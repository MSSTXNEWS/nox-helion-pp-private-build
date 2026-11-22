#!/bin/bash
curl -fsSL -H "Accept: application/vnd.github.raw" "https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/web/restart.py?ref=main" -o /tmp/restart.py
python3 /tmp/restart.py 8091 /root/nox/logs/web_server.log; sleep 3
echo "chat $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/chat.html)"; grep -c "stream\" in ctype" /root/nox/web_server.py
curl -sN -m60 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"stream":true,"nox_mode":"fast"}' | head -2 | cut -c1-120
