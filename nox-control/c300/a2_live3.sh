echo "C300: a2_live3"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/1cfd4fb510b019379d93035672b9268989da4ada/nox-control/c300; A=/workspace/nox/agents
for f in nox_agents.py nox_worms.py; do cp $A/$f $A/$f.bak_a2_l3; curl -fsSL "$R/$f" -o $A/$f.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/$f.new').read())" && mv $A/$f.new $A/$f || echo FAIL $f; done
curl -fsSL "$R/a2_live2.py" -o $A/a2_live2.py; grep -c "breaker" $A/nox_agents.py; grep -c "Правило из урока" $A/nox_worms.py
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15; setsid -f sh -c "$A/venv/bin/python $A/a2_live2.py > $A/live2.log 2>&1" </dev/null >/dev/null 2>&1
sleep 60; cat $A/live2.log | cut -c1-300
