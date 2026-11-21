#!/bin/bash
echo "== gw health"; for p in 8083 18098 8082; do echo "$p $(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/health)"; done
echo "== fast tier speed"
curl -s -m 60 http://127.0.0.1:8083/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Скажи одним предложением по-русски, что такое Луна."}],"max_tokens":60,"chat_template_kwargs":{"enable_thinking":false}}' -w "\ntime=%{time_total}\n" | python3 -c "import sys;t=sys.stdin.read();print(t[-700:])"
echo "== glm speed"
curl -s -m 120 http://127.0.0.1:18098/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Скажи одним предложением по-русски, что такое Луна."}],"max_tokens":40}' -w "\ntime=%{time_total}\n" | python3 -c "import sys;t=sys.stdin.read();print(t[-700:])"
echo "== tts voices"; grep -n "lang\|voice\|onnx" /root/nox/repo/nox-control/voice/tts_server.py | grep -iE "ru_RU|PIPER_VOICE|default|auto" | head -8 | cut -c1-200; ls /root/nox/dl/hf/piper_ru 2>/dev/null | head
uptime; free -g | sed -n 2p; ps aux --sort=-%cpu | head -6 | cut -c1-150
