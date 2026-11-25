for u in /api/chat/health /glm/v1/nox/stats /web/data/live.json /cal/events; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{time_total}' -m10 http://127.0.0.1:8091$u)"; done
curl -s -m60 -X POST http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"model":"nox","stream":true,"messages":[{"role":"user","content":"скажи да"}]}' | head -c 300; echo
pgrep -af "web_server|run_web" | cut -c1-120
ls -t /workspace/nox/agent/out/ | head -5
tail -15 /workspace/nox/agent/out/web.log 2>/dev/null | cut -c1-220
grep -n "Basic\|auth_off\|X-Forwarded" /workspace/nox/web/pkg/server/*.py | head -8
