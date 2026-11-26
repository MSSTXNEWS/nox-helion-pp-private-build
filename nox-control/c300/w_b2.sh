echo "C300: w_b2"
N=/workspace/nox
echo "--caddy structure (only routing lines)"; grep -n -i -E '^\s*(:|handle|route|reverse_proxy|@|respond|file_server|root|bind|}$)|^[^ \t]+ *\{' $N/ops/web_chat_auth/Caddyfile | grep -i -v -E 'auth|hash|pass|token|secret|bearer|\$2' | cut -c1-120 | head -60
echo "--sup"; ls /etc/supervisor/conf.d | head -30
f=$(ls /etc/supervisor/conf.d/* | head -1); sed -n '1,12p' $f | grep -v -i -E 'pass|token|secret|key'
echo "--verdict"; python3 -c "import json;d=json.load(open('$N/state/p3/train_verdict.json'));print({k:(v if not isinstance(v,(dict,list)) else type(v).__name__) for k,v in d.items()})"
python3 -c "import json;d=json.load(open('$N/agent/out/round_last.json'));print({k:(v if not isinstance(v,(dict,list)) else type(v).__name__) for k,v in d.items()})" | cut -c1-500
tail -c 300 $N/agent/out/round_best_history.jsonl
echo "--agenda/settings"; ls $N/state | grep -i -E 'agenda|settings|ui_'
curl -s -m5 http://127.0.0.1:8810/openapi.json | python3 -c "import sys,json;print(list(json.load(sys.stdin)['paths']))" 2>&1 | cut -c1-700
echo "--ports 86xx/87xx"; ss -ltn | grep -E ':(86|87)[0-9]{2}\b'
