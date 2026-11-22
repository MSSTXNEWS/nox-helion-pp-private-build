#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/ui4.py -o /tmp/ui4.py && python3 /tmp/ui4.py
node -e "new Function(require('fs').readFileSync('/root/nox/web/nox_mode.js','utf8'))" && echo js ok
curl -s -m5 -o /dev/null -w "chat %{http_code}\n" http://127.0.0.1:8091/web/chat.html; curl -s -m5 -o /dev/null -w "js %{http_code}\n" http://127.0.0.1:8091/web/nox_mode.js
head -c 300 /root/nox/web/sw.js
