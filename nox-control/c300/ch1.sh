curl -s -m60 -X POST http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"model":"nox","stream":true,"messages":[{"role":"user","content":"Привет, ответь одним словом"}]}' | head -c 600; echo
echo "--health"; curl -s -m10 http://127.0.0.1:8090/health | head -c 900; echo
for p in 8082 8084 8090 8104 8200 8400 8510; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:$p/health) $(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:$p/v1/models)"; done
curl -s -m60 http://127.0.0.1:8104/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"скажи да"}],"max_tokens":50,"chat_template_kwargs":{"enable_thinking":false}}' | head -c 400; echo
tail -5 /workspace/nox/agent/out/web*.log 2>/dev/null | cut -c1-300
grep -n "api/chat" /workspace/nox/web/pkg/server/web_server.py | head -5
