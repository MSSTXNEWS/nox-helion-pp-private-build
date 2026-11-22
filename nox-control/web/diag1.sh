#!/bin/bash
W=/root/nox/web
echo "== health"; for p in 8082 8083 8081; do echo "$p $(curl -s -m3 http://127.0.0.1:$p/health | head -c 120)"; done
echo "== 8083 chat"; curl -s -m40 http://127.0.0.1:8083/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"max_tokens":60,"stream":false}' | head -c 700; echo
echo "== 8091 /api/chat fast (как браузер)"; curl -s -m60 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"model":"nox","messages":[{"role":"user","content":"привет"}],"stream":true,"options":{"nox_mode":"fast"},"nox_mode":"fast"}' | head -c 900; echo
echo "== nox_mode.js"; wc -c $W/nox_mode.js; grep -o "\[\['[^]]*\]\(,\['[^]]*\]\)*\]" $W/nox_mode.js | head -2 | cut -c1-300
echo "== web_server chat"; grep -n "nox_mode\|fast\|8083\|reasoning\|think" /root/nox/web_server.py | head -25 | cut -c1-230
