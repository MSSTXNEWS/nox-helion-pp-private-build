#!/bin/bash
echo "== health"; curl -s -m 5 http://127.0.0.1:8091/tts/health | head -c 600; echo
echo "== synth wav"; curl -s -m 90 -o /tmp/t.wav -w "http=%{http_code} bytes=%{size_download}\n" -X POST http://127.0.0.1:8091/tts/synth -H 'Content-Type: application/json' -d '{"text":"Привет, мессир. Проверка голоса.","lang":"ru","format":"wav"}'; head -c 4 /tmp/t.wav; echo; head -c 300 /tmp/t.wav | strings | head -3
echo "== session flow"
S=$(curl -s -m 20 -X POST http://127.0.0.1:8091/tts/session -H 'Content-Type: application/json' -d '{"lang":"ru"}'); echo "$S"
ID=$(echo "$S" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('id') or d.get('session') or d.get('session_id') or '')")
curl -s -m 20 -X POST http://127.0.0.1:8091/tts/session/$ID/text -H 'Content-Type: application/json' -d '{"text":"Проверка голоса. Раз, два, три.","final":true}' | head -c 300; echo
timeout 60 curl -s -N -m 60 "http://127.0.0.1:8091/tts/session/$ID/audio?format=sse" | head -c 400; echo
echo "== log"; tail -15 /root/nox/logs/tts*.log 2>/dev/null | cut -c1-220
