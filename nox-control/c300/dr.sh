#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/dr.py -o /tmp/dr.py && python3 /tmp/dr.py
bash /workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -2
for u in /drive/ /api/chat/health /web/chat.html /web/vendor/glasskit/glasskit.min.css /tts/health /stt/health; do echo "$u $(curl -s -m8 -o /tmp/u.b -w %{http_code} 127.0.0.1:8091$u) $(head -c 100 /tmp/u.b | tr '\n' ' ')"; done
tail -6 /workspace/nox/agent/out/c300_voice.log | cut -c1-200
