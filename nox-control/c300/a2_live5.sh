echo "C300: a2_live5"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/1abd38d23f5f43c8c812030271894035536c043d/nox-control/c300; A=/workspace/nox/agents
cp $A/nox_agents.py $A/nox_agents.py.bak_a2_l5; curl -fsSL "$R/nox_agents.py" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
curl -fsSL "$R/a2_live4.py" -o $A/a2_live4.py; grep -c "pollinations/auto" $A/nox_agents.py
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15; setsid -f sh -c "$A/venv/bin/python $A/a2_live4.py > $A/live4.log 2>&1" </dev/null >/dev/null 2>&1
sleep 5; echo started
