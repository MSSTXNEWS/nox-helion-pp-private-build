I=127.0.0.1:8091
curl -s -m 10 "$I/svc/invoke/api/v2/models/?model_type=main" | head -c 600; echo
curl -s -m 10 "$I/svc/invoke/api/v1/images/?limit=5" | head -c 400; echo
curl -s -m 10 -i "$I/img/generate" | head -12; curl -s -m 10 "$I/img/health" | head -c 400; echo
grep -n "img/generate\|/img/" /workspace/nox/web/pkg/server/web_server.py | head -8 | cut -c1-240
grep -rn "img/generate" /workspace/nox/web/site/*.js | cut -c1-300 | head -5
