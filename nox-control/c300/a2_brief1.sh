echo "C300: a2_brief1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; W=/workspace/nox; A=$W/agents; P=$W/state/playbooks
mkdir -p $P
cat > $P/_base.yaml <<'Y'
БРИФ МЕТОДОЛОГА (обязателен для каждого субисполнителя)
1) Сначала фундамент: анализ среды -> готовое из интернета (библиотеки, лучшие практики) -> оптимизация основы с замером -> функции -> проверка и урок.
2) Только готовое; свой код лишь клей.
3) Собирай и тестируй офлайн/локально/на копии; на прод переноси один раз пакетом; шаги объединяй в пакеты; долгое запускай в фоне.
4) «добавь» не означает «останови/перенеси»; текущее не трогай.
5) Чистки только по белому списку и с проверкой импортов.
6) Владельца спрашивай только о деньгах, доступах и удалениях; остальное решай сам и запиши допущение.
Y
echo "Плейбук cleanup: белый список путей -> проверка импортов (grep/ast) -> бэкап -> удаление -> тест -> откат при ошибке." > $P/cleanup.yaml
echo "Плейбук server: железо -> драйверы -> тюнинг -> ускорители -> бенчмарк -> сервисы." > $P/server.yaml
echo "Плейбук page: лидер ниши -> готовые движки/компоненты -> сборка -> QA (кликнуть все кнопки)." > $P/page.yaml
cp $A/nox_agents.py $A/nox_agents.py.bak_a2_$(date +%H%M)
curl -fsSL "$R/nox_agents.py?$(date +%s)" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
pkill -f 'nox_agents.py'; sleep 3; cd $A && nohup setsid $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1 &
sleep 12; curl -s -m5 127.0.0.1:8810/health | head -c 150; echo
mk(){ curl -s -m20 -X POST 127.0.0.1:8810/task -H 'Content-Type: application/json' -d "$1"; echo; }
mk '{"title":"hello-func","goal":"Напиши python-функцию slugify(text) и тест к ней","role":"coder"}'
mk '{"title":"readme","goal":"Напиши короткий README про сервис очередей, 5 строк","role":"writer"}'
mk '{"title":"deploy-script","goal":"Напиши python-скрипт deploy.py, который перезапускает сервис NOX через systemctl restart nox-web и пишет лог","role":"coder"}'
sleep 150
curl -s 127.0.0.1:8810/tasks | python3 -c "
import json,sys,urllib.request
for t in json.load(sys.stdin)[:3]:
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8810/task/'+t['id']))
    st=d.get('steps',[])
    print(t['id'],t['title'],t['status'],'brief',sum(s['kind']=='brief' for s in st),'coach',[s['text'][:90] for s in st if s['kind']=='coach'])
"
curl -s 127.0.0.1:8810/metrics | head -c 400; echo
