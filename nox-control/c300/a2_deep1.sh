echo "C300: a2_deep1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/5111dc33fd1f569ddec64677026bffb8370e56eb/nox-control/c300; A=/workspace/nox/agents
curl -s -m10 127.0.0.1:8810/task/1125-5f4b62 | python3 -c "
import json,sys;d=json.load(sys.stdin);print('coach task',d['status'])
for s in d['steps']:
    if s['kind'] in ('coach','review','lesson','stopper','brief'): print(' ',s['kind'],s['text'][:170].replace('\n',' '))
print(' artifacts',[a['path'] for a in (d.get('result') or {}).get('artifacts',[])])"
st=$(curl -s -m10 127.0.0.1:8810/task/1125-5f4b62 | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])")
echo "status=$st"
if [ "$st" != running ] && [ "$st" != queued ]; then
  cp $A/nox_agents.py $A/nox_agents.py.bak_a2_dp; curl -fsSL "$R/nox_agents.py" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
  pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
  cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
  sleep 15
  setsid -f sh -c "curl -s -m 280 -X POST 127.0.0.1:8810/consilium -H 'Content-Type: application/json' -d '{\"question\":\"Как лучше хранить уроки из ошибок агентов: файл, БД или граф знаний?\",\"deep\":true,\"budget\":200}' > $A/cons_deep2.json" </dev/null >/dev/null 2>&1
  sleep 150
  python3 -c "
import json;d=json.load(open('$A/cons_deep2.json'));print('DEEP',d['seconds'],'s senior',d.get('senior'),'waves',[(w['wave'],[o['advisor'] for o in w['opinions']]) for w in d['waves']],'err',d.get('errors'));print(d['final'][:300])" 2>&1 | tail -4
else echo "коуч-задача ещё идёт, деплой отложен"; fi
