export RUNNER_TRACKING_ID=""
echo "C300: tr_cad1"
ps -eo pid,args | grep -E "[c]addy" | cut -c1-160 | head -3
CF=$(ps -eo args | grep -oE "\-\-config [^ ]+" | head -1 | cut -d' ' -f2); echo "cfg=$CF"
[ -n "$CF" ] || CF=$(ls /workspace/nox/*/Caddyfile /workspace/nox/Caddyfile /etc/caddy/Caddyfile 2>/dev/null | head -1); echo "cfg=$CF"; wc -l $CF
grep -n -i -E "18091|memory|18220|reverse_proxy|handle|route|^[a-z:\[]" $CF | cut -c1-170 | head -70
for u in /memory/health /api/nox/memory/health /api/nox/memory/recall; do echo "$u -> $(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:18091$u)"; done
echo "-- :18220"; ss -ltnp | grep 18220 | awk '{print $4,$6}' | cut -c1-80; for u in /health /memory/health /api/health; do echo "18220$u -> $(curl -s -m5 -w ' [%{http_code}]' http://127.0.0.1:18220$u | head -c 200)"; done
curl -s -m5 http://127.0.0.1:18220/openapi.json | python3 -c "import json,sys;print(list(json.load(sys.stdin).get('paths',{}))[:20])" 2>&1 | head -2
grep -rn "memory/health" /workspace/nox/web/*.js /workspace/nox/web/*.html /workspace/nox/svc 2>/dev/null | cut -c1-140 | head -4
echo END
