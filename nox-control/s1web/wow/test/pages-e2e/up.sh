#!/bin/bash
# поднять стенд: fake llama x2, настоящий gateway :8082, recall :8095, fake tts :8094, web :18091
cd /tmp/st
GW=/tmp/claude-0/wt-pages/nox-control/glm53/gateway.py
pkill -f "GATE_FAKE_LLAMA|glm53/gateway.py|qs6.recall_server|fake_tts.py|web_server.py" 2>/dev/null; sleep 1
setsid nohup python3 /tmp/final/GATE_FAKE_LLAMA.py 18081 >/tmp/st/l1.log 2>&1  </dev/null &
setsid nohup python3 /tmp/final/GATE_FAKE_LLAMA.py 18083 >/tmp/st/l2.log 2>&1  </dev/null &
sleep 1
NOX_UPSTREAM=http://127.0.0.1:18081 NOX_FAST_UPSTREAM=http://127.0.0.1:18083 setsid nohup python3 $GW >/tmp/st/gw.log 2>&1  </dev/null &
(cd /tmp/claude-0/wt-pages/nox-control && NOX_MEMORY_DB=/tmp/st/s03.db setsid nohup python3 -m qs6.recall_server >/tmp/st/mem.log 2>&1 &)
grep -n "8094\|PORT\|serve_forever" /tmp/vt/fake_tts.py | head -3
setsid nohup python3 /tmp/st/fakevoice.py >/tmp/st/voice.log 2>&1  </dev/null &
NOX_WEB_ROOT=/tmp/pagesroot NOX_WEB_PORT=18091 setsid nohup python3 /tmp/vt/web_server.py >/tmp/st/web.log 2>&1  </dev/null &
sleep 2
for u in /web/chat.html /glm/v1/models /glm/v1/nox/stats /memory/health /tts/health /stt/health; do echo "$u $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:18091$u)"; done
