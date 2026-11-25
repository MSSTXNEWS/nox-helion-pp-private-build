echo "C300: a2_deploy5"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/11c06f19e66ff14518f8be70cfa7e545501cc756/nox-control/c300; A=/workspace/nox/agents
cp $A/nox_agents.py $A/nox_agents.py.bak_a2_d5; curl -fsSL "$R/nox_agents.py" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
grep -c "иду к внешним советникам" $A/nox_agents.py
echo "== кто держит слоты 8104"; ss -tnp 2>/dev/null | grep ':8104' | awk '{print $5, $6}' | sort | uniq -c | sort -rn | head -12
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 200
curl -s -m10 127.0.0.1:8810/board | python3 -c "
import json,sys
b=json.load(sys.stdin)
for k in ('Нужен ты','В работе','Готово'):
    for c in b[k][:8]: print(k,c['id'],c['title'][:20],c['stage'],c['pct'],c['blocker'][:60])"
curl -s -m10 127.0.0.1:8810/tasks | python3 -c "
import json,sys,urllib.request
for t in json.load(sys.stdin)[:30]:
    if t['title'] not in ('c1-slugify','c2-readme','c3-restart'): continue
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8810/task/'+t['id'],timeout=10))
    print(t['id'],t['title'],t['status'],[ (s['kind'],s['text'][:70]) for s in d['steps'][-6:]])
    print('  artifacts',(d.get('result') or {}).get('artifacts'))"
