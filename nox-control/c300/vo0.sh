#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/vo.sh -o /workspace/nox/c300_vo.sh && (nohup setsid bash /workspace/nox/c300_vo.sh >/dev/null 2>&1 </dev/null &) && echo started
W=/workspace/nox/web/pkg/server/web_server.py; grep -n "def _proxy\|self._proxy(\"GET\"" $W | head -5 | cut -c1-200; grep -n 'if p == "/api/pc-metrics"\|if p.startswith("/tts/")' $W | head -3 | cut -c1-160
grep -rn "glasskit" /workspace/nox/web/site/*.html | head -3 | cut -c1-160; cat /root/onstart.sh | head -12 | cut -c1-160
