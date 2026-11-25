echo "C300: a2_ops2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/cff938156a288686500f9db90e1c347e3b9edbc2/nox-control/c300; A=/workspace/nox/agents
cp $A/book.sqlite $A/book.sqlite.bak_a2_ops2
python3 - <<'P'
import sqlite3,time
c=sqlite3.connect('/workspace/nox/agents/book.sqlite')
n=c.execute("update tasks set status='cancelled', finished=? where status in ('needs_owner','failed')",(time.time(),)).rowcount; c.commit(); print('закрыто тестовых needs_owner/failed:',n)
open('/workspace/nox/state/lessons.jsonl','a').write('{"ts":%d,"task":"ops","src":"stall","what":"9 тестовых задач ушли в needs_owner при исчерпанном пуле советников","why":"тесты шли на общей квоте, пул отдавал 502","rule":"тестовые прогоны только с x_nox_prio<=0 (кэш или локальные модели); при 502 пула не копить needs_owner, а ждать","repeat":0}\n' % time.time())
P
curl -fsSL "$R/nox_worms.py" -o $A/nox_worms.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_worms.py.new').read())" && cp $A/nox_worms.py $A/nox_worms.py.bak_a2_ops2 && mv $A/nox_worms.py.new $A/nox_worms.py || echo FAIL
grep -c "def night_loop" $A/nox_worms.py
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15; curl -s -m5 127.0.0.1:8810/health | head -c 80; echo
mk(){ curl -s -m20 -X POST 127.0.0.1:8810/task -H 'Content-Type: application/json' -d "$1"; echo; }
mk '{"title":"c7-fizzbuzz","goal":"Напиши python-функцию fizzbuzz(n) и pytest-тест","role":"coder","source":"chat"}'
mk '{"title":"c7-readme","goal":"Напиши README на 5 строк про карточки червей NOX","role":"writer","source":"chat"}'
curl -s -m10 -X POST 127.0.0.1:8810/worms/night/run; echo
curl -s -m10 127.0.0.1:8810/worms/agenda/check; echo
sleep 150
curl -s -m10 127.0.0.1:8810/worms/night | head -c 400; echo
for t in c7-fizzbuzz c7-readme; do id=$(curl -s 127.0.0.1:8810/tasks | python3 -c "import json,sys;print(next(x['id'] for x in json.load(sys.stdin) if x['title']=='$t'))"); curl -s -m10 127.0.0.1:8810/task/$id/receipt | head -c 450; echo; done
curl -s -m10 127.0.0.1:8810/board | python3 -c "import json,sys;print({k:len(v) for k,v in json.load(sys.stdin).items()})"
