echo "C300: a2_live1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/1a750ba6a502c6542d8cfa3e9514a399579046ab/nox-control/c300; A=/workspace/nox/agents
cp $A/nox_agents.py $A/nox_agents.py.bak_a2_l1; curl -fsSL "$R/nox_agents.py" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
for f in a2_eval_llm.py a2_worms_live.py a2_coach_test.py; do curl -fsSL "$R/$f" -o $A/$f || echo FAIL $f; done
grep -c "def get_receipt" $A/nox_agents.py
curl -s -m10 -X POST 127.0.0.1:8810/task/1125-ec237e/cancel; echo
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15
echo "== coach unit test"; $A/venv/bin/python $A/a2_coach_test.py
setsid -f sh -c "python3 $A/a2_eval_llm.py > $A/eval_llm.log 2>&1; curl -s -m 200 -X POST 127.0.0.1:8810/consilium -H 'Content-Type: application/json' -d '{\"question\":\"Что лучше для очереди задач на одном сервере: SQLite или Redis?\",\"budget\":100}' > $A/cons_n.json; curl -s -m 260 -X POST 127.0.0.1:8810/consilium -H 'Content-Type: application/json' -d '{\"question\":\"Как лучше организовать уроки из ошибок для самообучения агентов?\",\"deep\":true,\"budget\":150}' > $A/cons_d.json" </dev/null >/dev/null 2>&1
setsid -f sh -c "$A/venv/bin/python $A/a2_worms_live.py > $A/worms_live.log 2>&1" </dev/null >/dev/null 2>&1
sleep 100; tail -5 $A/eval_llm.log | cut -c1-200; tail -8 $A/worms_live.log | cut -c1-250
