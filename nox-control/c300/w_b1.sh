echo "C300: w_b1"
N=/workspace/nox
echo "--supervisor"; which supervisord supervisorctl; ls /etc/supervisor* /workspace/nox/*supervis* 2>&1 | head -20; ps aux | grep -E 'supervisord|caddy' | grep -v grep | cut -c1-200
echo "--caddy"; find / -name 'Caddyfile*' -not -path '*/proc/*' 2>/dev/null | head; 
echo "--ports"; ss -ltnp 2>/dev/null | awk '{print $4,$6}' | cut -c1-90 | head -40
echo "--py"; $N/venv/bin/python -c "import aiohttp;print('aiohttp',aiohttp.__version__)" 2>&1; $N/venv/bin/python -c "import fastapi,uvicorn;print('fastapi')" 2>&1 | tail -1
echo "--state"; ls -la $N/state/p3/train_verdict.json $N/state/ui_settings.json 2>&1; ls $N/state | head -30
echo "--8810"; for p in /board /worms/learned /agenda /health; do echo "$p:"; curl -s -m 5 -w ' [%{http_code}]' http://127.0.0.1:8810$p | cut -c1-400; echo; done
echo "--rounds"; ls $N/agent/out 2>/dev/null | grep -i -E 'round|autotrain' | head; ls $N/state/p3 | head -20
echo "--18091"; curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18091/; curl -s -m5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/api/status
