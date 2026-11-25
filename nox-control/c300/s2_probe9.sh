#!/bin/bash
S=/workspace/nox/web/site
echo "--vidstack"; ls -la $S/vendor/vidstack | head -20; ls $S/vendor/vidstack/player 2>/dev/null | head; find $S/vendor/vidstack -name "*.css" | head
echo "--whisperlive"; ls /workspace/nox/svc 2>/dev/null | head -40
curl -s -m5 -o /dev/null -w "wl18209 %{http_code}\n" http://127.0.0.1:18209/
curl -s -m5 -o /dev/null -w "svc/wl %{http_code}\n" http://127.0.0.1:8091/svc/whisperlive/
echo "--podcastfy"; curl -s -m5 -w "\n%{http_code}\n" http://127.0.0.1:18208/ | head -c 600
curl -s -m5 http://127.0.0.1:18208/openapi.json | head -c 1500
echo; echo "--llm"; curl -s -m5 http://127.0.0.1:8104/v1/models | head -c 300
echo; curl -s -m5 http://127.0.0.1:8091/glm/v1/models | head -c 300
echo "--chat timing"
time (curl -s -m100 -N -X POST http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"stream":true,"nox_mode":"fast","messages":[{"role":"user","content":"Верни ТОЛЬКО JSON {\"nodes\":[{\"id\":1,\"text\":\"a\"}]} для идей: маркетинг, финансы"}]}' | head -c 1500)
