echo "C300: a2_deploy4"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/0d9dea98be15d58cc07cb6325a5fbe8a78e6ab48/nox-control/c300; A=/workspace/nox/agents
for f in nox_agents.py nox_worms.py; do cp $A/$f $A/$f.bak_a2_d4; curl -fsSL "$R/$f" -o $A/$f.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/$f.new').read())" && mv $A/$f.new $A/$f || echo FAIL $f; done
curl -fsSL "$R/golden_intents.json" -o /workspace/nox/agents/golden_intents.json || echo FAIL golden
grep -c "def consilium_ext" $A/nox_agents.py
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15
J(){ curl -s -m "$1" "${@:2}"; echo; }
echo "== eval"; J 60 127.0.0.1:8810/intents/eval | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['n'],d['ok'],d['share']);[print(' FAIL',c['phrase']) for c in d['cases'] if not c['ok']]"
(setsid -f sh -c "curl -s -m 200 -X POST 127.0.0.1:8810/consilium -H 'Content-Type: application/json' -d '{\"question\":\"Что лучше для очереди задач на одном сервере: SQLite или Redis?\",\"deep\":true,\"budget\":120}' > $A/cons_deep.json" </dev/null >/dev/null 2>&1)
echo "== consilium shallow"; J 150 -X POST 127.0.0.1:8810/consilium -H 'Content-Type: application/json' -d '{"question":"Что лучше для очереди задач на одном сервере: SQLite или Redis?","budget":90}' | python3 -c "
import json,sys;d=json.load(sys.stdin);print('sec',d['seconds'],'avail',d['advisors_available']);[print(' w',w['wave'],[(o['advisor'],o['text'][:60]) for o in w['opinions']]) for w in d['waves']];print('FINAL',d['final'][:300])"
echo "== worms rescan"; (setsid -f sh -c "curl -s -m 280 -X POST 127.0.0.1:8810/worms/scan > $A/scan2.json" </dev/null >/dev/null 2>&1)
J 10 127.0.0.1:8810/board | python3 -c "
import json,sys
b=json.load(sys.stdin)
for k in ('В работе','Готово','Нужен ты'):
    for c in b[k][:5]: print(k,c['id'],c['title'][:20],c['stage'],c['pct'])"
