#!/bin/bash
echo "== api/chat ru"; curl -s -m 60 -N http://127.0.0.1:8091/api/chat -d '{"request_id":"t1","model":"nox-helion:latest","messages":[{"role":"user","content":"Привет, кто ты?"}],"options":{}}' | head -c 900; echo
echo "== v1 fast"; curl -s -m 60 http://127.0.0.1:8082/v1/chat/completions -H 'content-type: application/json' -d '{"model":"nox","stream":false,"messages":[{"role":"user","content":"Скажи привет одним предложением"}]}' | head -c 600; echo
ls /root/nox/glm53 | head -13; ls -la /root/nox/glm53_disk | head -5; grep -E "ALL_OK|SOME_BAD| OK| BAD" /root/nox/logs/redo.log | tail -12 | cut -c1-100
