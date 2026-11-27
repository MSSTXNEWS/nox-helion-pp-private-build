export RUNNER_TRACKING_ID=""
echo "C300: tr_cad2"
for p in 18091 8091 18220 8796; do echo "== :$p"; ss -ltnp | grep ":$p " | grep -oE 'users:\(\("[^"]+",pid=[0-9]+' | head -2; done
P=$(ss -ltnp | grep ":18091 " | grep -oP 'pid=\K[0-9]+' | head -1); ps -o pid,etimes,args -p $P | cut -c1-200
P2=$(ss -ltnp | grep ":18220 " | grep -oP 'pid=\K[0-9]+' | head -1); ps -o pid,etimes,args -p $P2 | cut -c1-200
ls /workspace/nox/stewards 2>/dev/null | grep -i -E "caddy|bridge|front|18091" | head; ls /workspace/nox | grep -i -E "caddy|bridge" | head
for u in /memory/health /api/nox/memory/health /api/health /; do echo "18091$u -> $(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:18091$u)"; done
for u in /health /memory/health /status /stats; do echo "18220$u -> $(curl -s -m5 -w ' [%{http_code}]' http://127.0.0.1:18220$u | head -c 160)"; done
curl -s -m5 http://127.0.0.1:18220/openapi.json | python3 -c "import json,sys;print(list(json.load(sys.stdin).get('paths',{}))[:20])" 2>&1 | head -2
echo END
