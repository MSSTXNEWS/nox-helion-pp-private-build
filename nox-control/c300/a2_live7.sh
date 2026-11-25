echo "C300: a2_live7"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/8ec4fb24d103e2832b9aeb1f109ec62ac8369247/nox-control/c300; A=/workspace/nox/agents
for f in nox_agents.py nox_worms.py; do cp $A/$f $A/$f.bak_a2_l7; curl -fsSL "$R/$f" -o $A/$f.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/$f.new').read())" && mv $A/$f.new $A/$f || echo FAIL $f; done
for f in passport_prompt.json a2_eval_llm.py a2_live6.py; do curl -fsSL "$R/$f" -o $A/$f || echo FAIL $f; done
curl -fsSL "$R/LESSONS.md" -o /workspace/nox/LESSONS.md
grep -c "agenda_loop" $A/nox_worms.py; grep -c "passport_llm" $A/nox_agents.py
$A/venv/bin/pip install -q mistune markdown-it-py 2>&1 | tail -1
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15; curl -s -m5 127.0.0.1:8810/health | head -c 100; echo
setsid -f sh -c "$A/venv/bin/python $A/a2_live6.py > $A/live6.log 2>&1" </dev/null >/dev/null 2>&1
sleep 3; echo started
