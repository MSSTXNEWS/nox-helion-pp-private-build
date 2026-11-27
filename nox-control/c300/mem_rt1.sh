echo "K1: mem_rt1"
CF=/workspace/nox/ops/web_chat_auth/Caddyfile
grep -nE "memory|18220|handle|reverse_proxy" $CF | grep -viE "basic|hash|password|token|key" | head -30
for p in health list recall remember forget search facts stats; do echo "18220/$p GET=$(curl -s -o /dev/null -m 4 -w %{http_code} http://127.0.0.1:18220/$p)"; done
curl -s -m 4 http://127.0.0.1:18220/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);print('paths',' '.join(sorted(d.get('paths',{}).keys())))" 2>/dev/null
