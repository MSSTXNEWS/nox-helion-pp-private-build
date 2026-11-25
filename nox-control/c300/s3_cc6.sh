P=/workspace/nox/web/pkg/server
post(){ curl -s -m 60 -X POST localhost:8091$1 -H 'Content-Type: application/json' -d "$2" | head -c 600; echo; }
echo "== CC6"
echo "T chat:"; post /api/chat '{"messages":[{"role":"user","content":"Ответь одним словом: тест"}],"stream":false}'
echo "T health $(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health)"
echo "T navidrome before $(curl -s -m 5 -o /dev/null -w '%{http_code}' 127.0.0.1:4533/svc/navidrome/ )"
R=$(curl -s -m 10 -X POST localhost:8091/api/cmd/confirm -H 'Content-Type: application/json' -d '{"name":"svc.restart"}'); echo "T confirm: $(echo $R | head -c 60)..."
TOK=$(echo "$R" | /workspace/nox/venv/bin/python -c "import sys,json;print(json.load(sys.stdin).get('confirm_token',''))")
echo "T restart navidrome:"; post /api/cmd "{\"name\":\"svc.restart\",\"params\":{\"service\":\"navidrome\"},\"confirm_token\":\"$TOK\"}"
sleep 8; echo "T navidrome after $(curl -s -m 5 -o /dev/null -w '%{http_code}' 127.0.0.1:4533/svc/navidrome/ ) port $( (echo > /dev/tcp/127.0.0.1/4533) 2>/dev/null && echo up || echo down)"
echo "T reuse token:"; post /api/cmd "{\"name\":\"svc.restart\",\"params\":{\"service\":\"navidrome\"},\"confirm_token\":\"$TOK\"}"
tail -3 /workspace/nox/state/cmd_log.jsonl | cut -c1-200
