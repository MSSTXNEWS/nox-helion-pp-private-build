echo "C300: a2_race1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/0f717de5a5abb1899ebb0e84bf9aa98fbadf8c89/nox-control/c300; A=/workspace/nox/agents
cp $A/nox_agents.py $A/nox_agents.py.bak_a2_r1; curl -fsSL "$R/nox_agents.py" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
grep -c "гонка" $A/nox_agents.py
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15
for i in 1 2 3; do curl -s -m 60 -X POST 127.0.0.1:8810/llm -H 'Content-Type: application/json' -d '{"prompt":"Скажи одним словом: столица Франции?","max_tokens":20}' | head -c 250; echo; done
curl -s -m5 127.0.0.1:8810/metrics | head -c 450; echo
echo "== live2.log"; cut -c1-600 $A/live2.log
