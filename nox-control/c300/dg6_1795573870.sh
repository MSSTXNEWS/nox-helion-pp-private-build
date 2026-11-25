grep -n "уже идёт ответ\|api/chat/stop" /workspace/nox/web/pkg/server/*.py | head -5
curl -s -m10 http://127.0.0.1:8090/health | python3 -c "import json,sys;d=json.load(sys.stdin);print('running',d.get('running'),'glm',d.get('glm'),'fast',d.get('fast'))"
curl -s -m10 -X POST http://127.0.0.1:8091/api/chat/stop -H 'Content-Type: application/json' -d '{}' | head -c 300; echo
sleep 3
curl -s -m60 -X POST http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"model":"nox","stream":true,"messages":[{"role":"user","content":"скажи привет"}]}' | head -c 400; echo
ls -t /workspace/nox/web/site/qa/rework/*.fixed 2>/dev/null | head; cat /workspace/nox/web/site/qa/summary.md 2>/dev/null | head -20
