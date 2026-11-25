echo "C300: a2_probe3"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/5338674b999603585e83609749fd5996917a6f8e/nox-control/c300; A=/workspace/nox/agents
cp $A/nox_agents.py $A/nox_agents.py.bak_a2_ps
curl -fsSL "$R/nox_agents.py" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
grep -c "class PSem" $A/nox_agents.py
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15
J(){ curl -s -m "$1" "${@:2}"; echo; }
echo "== worms"; J 20 127.0.0.1:8810/worms | head -c 700
echo "== cards"; J 20 127.0.0.1:8810/worms/cards | head -c 500
echo "== agenda"; J 20 127.0.0.1:8810/worms/agenda | head -c 400
echo "== learned"; J 20 127.0.0.1:8810/worms/learned | head -c 300
echo "== intents eval"; J 90 127.0.0.1:8810/intents/eval | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['n'],d['ok'],d['share']);[print(' FAIL',c['phrase'],c['got']) for c in d['cases'] if not c['ok']]"
echo "== gateway"; J 10 127.0.0.1:8793/v1/models | python3 -c "import json,sys;d=json.load(sys.stdin)['data'];print(len(d),'models; ok',sum(1 for m in d if m.get('status')=='ok'))"
echo "== consilium"; J 120 -X POST 127.0.0.1:8810/consilium -H 'Content-Type: application/json' -d '{"question":"Что лучше для очереди задач на одном сервере: SQLite или Redis? Ответь кратко.","rounds":1,"budget":90}' | head -c 1500
echo "== chat api"; J 10 127.0.0.1:8091/health | head -c 200; grep -o "think[a-z_]*\|deeper\|глубже" /workspace/nox/web/site/chat.html 2>/dev/null | sort | uniq -c | head
