echo "C300: a2_cycle1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; W=/workspace/nox; A=$W/agents; S=$W/state
cp $A/nox_agents.py $A/nox_agents.py.bak_a2_c$(date +%H%M)
curl -fsSL "$R/nox_agents.py?$(date +%s)" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
curl -fsSL "$R/LESSONS.md?$(date +%s)" -o $W/LESSONS.md
echo "- проверка импортов до удаления; чистка только по белому списку (урок: чистка удалила ops/draw)" >> $S/playbooks/_lessons.yaml
echo '{"ts":1,"task":"seed","src":"owner","what":"чистка удалила ops/draw","why":"не проверены импорты","rule":"проверка импортов до удаления; чистка только по белому списку","repeat":0}' >> $S/lessons.jsonl
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A && NOX_STALL_MIN=6 nohup setsid $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1 &
sleep 12; pgrep -fc 'python nox_agents.py'; curl -s -m5 127.0.0.1:8810/health | head -c 120; echo
mk(){ curl -s -m20 -X POST 127.0.0.1:8810/task -H 'Content-Type: application/json' -d "$1"; echo; }
mk '{"title":"c1-slugify","goal":"Напиши python-функцию slugify(text) и pytest-тест к ней","role":"coder"}'
mk '{"title":"c2-readme","goal":"Напиши README на 5 строк про очередь задач NOX","role":"writer"}'
mk '{"title":"c3-restart","goal":"Напиши скрипт restart.py: systemctl restart nox-web и лог","role":"coder"}'
curl -s -m10 127.0.0.1:8810/board | head -c 600; echo
