echo "C300: srv_k12"
cd /workspace/nox/tools
wc -l tools_gateway.py; grep -n "port\|PORT\|bind\|listen\|uvicorn\|Popen\|knowledge" tools_gateway.py | cut -c1-200 | head -25
grep -v "Knowledge Graph MCP" logs/gateway.log | tail -15 | cut -c1-250
ls -la logs/gateway.log; ps aux | grep -i "tools_gateway\|knowledge\|mcp" | grep -v grep | cut -c1-200 | head
grep -rn "tools_gateway" /workspace/nox/agent/nox_agents/supervisor.py /workspace/nox/agent/nox_agents/selfheal.py | cut -c1-220 | head -5
ls /workspace/nox/tools | head -30
grep -n "8143" -B3 -A3 /workspace/nox/agent/out/k_orch_bg.sh | head -15
ps aux | grep llama-server | grep -v grep | grep -o "\-\-port [0-9]*\|--alias [a-z_0-9]*" | paste - - | head
