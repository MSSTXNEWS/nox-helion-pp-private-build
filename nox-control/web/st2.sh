#!/bin/bash
cd /root/nox
sed -n 140,200p web_server.py | cut -c1-220
echo "== raw"; curl -sN -m60 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"stream":true}' | head -c 600; echo
echo "== gw direct"; curl -sN -m60 http://127.0.0.1:8082/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"stream":true,"nox_mode":"fast"}' | head -c 600; echo
echo "== core direct"; curl -sN -m60 http://127.0.0.1:8090/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"stream":true,"nox_mode":"fast"}' | head -c 600; echo
echo "== 8083"; curl -s -m5 http://127.0.0.1:8083/health | head -c 100; tail -n 5 logs/core.log | cut -c1-200
