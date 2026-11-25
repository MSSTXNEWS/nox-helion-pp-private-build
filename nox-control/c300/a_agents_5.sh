# A: развёртывание сервиса субисполнителей (порт 8810), бэкапы, svc_registry, start_extra, смоук-тест
W=/workspace/nox; A=$W/agents; ST=$W/state; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
mkdir -p $A/sandbox
for f in nox_agents.py agents_guard.py; do curl -fsSL "$R/$f?$(date +%s)" -o $A/$f.new && { [ -f $A/$f ] && cp $A/$f $A/$f.bak_a_$(date +%H%M); mv $A/$f.new $A/$f; } || echo FAIL $f; done
for f in agent_roles agent_backends teams owner_intents; do curl -fsSL "$R/$f.json?$(date +%s)" -o $ST/$f.json.new && { [ -f $ST/$f.json ] && cp $ST/$f.json $ST/$f.json.bak_a_$(date +%H%M); mv $ST/$f.json.new $ST/$f.json; } || echo FAIL $f; done
curl -fsSL "$R/golden.json?$(date +%s)" -o $A/golden.json
echo "== arbiter walk()"; sed -n 40,56p $W/agent/arbiter.py
echo "== CPU llama-servers for roles"
M=$W/models/agents
pgrep -f 'port 8811' >/dev/null || nohup setsid $W/bin/llama-server --host 127.0.0.1 --port 8811 -m $M/coder3b/qwen2.5-coder-3b-instruct-q4_k_m.gguf -ngl 0 -t 4 -c 8192 --parallel 2 --jinja --alias coder3b </dev/null >$A/coder3b.log 2>&1 &
pgrep -f 'port 8812' >/dev/null || nohup setsid $W/bin/llama-server --host 127.0.0.1 --port 8812 -m $M/trainer17b/Qwen3-1.7B-Q4_K_M.gguf -ngl 0 -t 2 -c 4096 --parallel 2 --jinja --alias trainer17b </dev/null >$A/trainer.log 2>&1 &
echo "== svc_registry (бэкап внутри d_svc_reg.py)"
python3 $W/svc/d_svc_reg.py agents 8810 base "Субисполнители" "Задачи/команды/консилиум: /svc/agents/ (POST /task, /team, /consilium, GET /task/<id>, /metrics)"
echo "== start_extra.sh"
SE=$W/svc/start_extra.sh; [ -f $SE.bak_a_agents ] || cp $SE $SE.bak_a_agents
grep -q nox_agents.py $SE || cat >> $SE <<'X'

# A: субисполнители NOX (порт 8810) + CPU-модели ролей (кодер 3B :8811, тренер 1.7B :8812) + страж
(echo > /dev/tcp/127.0.0.1/8811) 2>/dev/null || { nohup setsid /workspace/nox/bin/llama-server --host 127.0.0.1 --port 8811 -m /workspace/nox/models/agents/coder3b/qwen2.5-coder-3b-instruct-q4_k_m.gguf -ngl 0 -t 4 -c 8192 --parallel 2 --jinja --alias coder3b </dev/null >/workspace/nox/agents/coder3b.log 2>&1 & }
(echo > /dev/tcp/127.0.0.1/8812) 2>/dev/null || { nohup setsid /workspace/nox/bin/llama-server --host 127.0.0.1 --port 8812 -m /workspace/nox/models/agents/trainer17b/Qwen3-1.7B-Q4_K_M.gguf -ngl 0 -t 2 -c 4096 --parallel 2 --jinja --alias trainer17b </dev/null >/workspace/nox/agents/trainer.log 2>&1 & }
pgrep -f agents/nox_agents.py >/dev/null || (cd /workspace/nox/agents && nohup setsid /workspace/nox/agents/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1 &)
pgrep -f agents/agents_guard.py >/dev/null || (cd /workspace/nox/agents && nohup setsid /workspace/nox/agents/venv/bin/python agents_guard.py </dev/null >>guard.log 2>&1 &)
X
/workspace/nox/agents/venv/bin/pip install -q langgraph-checkpoint-sqlite 2>&1 | tail -1
pgrep -f agents/nox_agents.py >/dev/null && pkill -f agents/nox_agents.py; sleep 2
cd $A && nohup setsid $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1 &
sleep 8; echo "== health"; curl -s -m 5 127.0.0.1:8810/health; echo; curl -s -m 5 127.0.0.1:8091/svc/agents/ | head -c 300; echo
for p in 8811 8812; do for i in 1 2 3 4 5 6 7 8; do [ "$(curl -s -m 3 -o /dev/null -w %{http_code} 127.0.0.1:$p/health)" = 200 ] && break; sleep 5; done; echo "$p $(curl -s -m 3 -o /dev/null -w %{http_code} 127.0.0.1:$p/health)"; done
echo "== smoke"; T=$(curl -s -m 10 -H 'Content-Type: application/json' -d '{"title":"smoke","goal":"Создай solution.py с функцией add(a,b), возвращающей сумму, и test_solution.py с pytest-тестом","role":"coder"}' 127.0.0.1:8810/task); echo $T
ID=$(echo $T | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
for i in $(seq 1 40); do s=$(curl -s 127.0.0.1:8810/task/$ID | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])"); [ "$s" = done -o "$s" = needs_owner -o "$s" = failed ] && break; sleep 5; done
curl -s 127.0.0.1:8810/task/$ID | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['status'],d['tokens']);[print(' ',s['kind'],s['role'],s['text'][:160]) for s in d['steps']]"
cat $ST/agents_activity.json; echo; cat $ST/arbiter.json | head -c 300; echo; tail -5 $A/service.log
