#!/bin/bash
R=/root/nox/repo; git -C $R pull -q 2>&1|tail -1
echo "== vendor"; bash $R/nox-control/s1web/vendor_install.sh 2>&1 | tail -6 | cut -c1-160
echo "== planets"; timeout 150 bash $R/nox-control/c123/planets_s1.sh 2>&1 | tail -6 | cut -c1-160
df -h / | tail -1
for u in /web/chat.html /web/vendor/three/package.json /stt/health /tts/health /memory/health; do echo "$u $(curl -s -m 8 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091$u)"; done
echo "== chat"; curl -s -m 90 -N http://127.0.0.1:8091/api/chat -d '{"request_id":"t2","model":"nox-helion:latest","messages":[{"role":"user","content":"Привет. Ты где работаешь?"}],"options":{}}' | head -c 500; echo
