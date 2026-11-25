echo "C300: a2_cycle2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; A=/workspace/nox/agents
curl -fsSL "$R/nox_agents.py?$(date +%s)" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15; pgrep -fc 'python nox_agents.py'; curl -s -m5 127.0.0.1:8810/health | head -c 120; echo
curl -s -m10 127.0.0.1:8810/inspect; echo
