W=/workspace/nox; A=$W/agents
echo "== intents eval"; python3 -c "
import json;d=json.load(open('$A/intents_eval.json'));print(d['ok'],'/',d['n'],d['share'])
[print(' ',c['ok'],c['got'],c['stop_current'],c['phrase']) for c in d['cases'] if not c['ok']]" 2>&1 | head -20
echo "== proxy через :1111 (basic auth из secrets, без вывода)"; AU=$(cat $W/secrets/web_basic_auth.txt | tr -d '\n'); for p in /svc/agents/ /svc/agents/metrics; do echo "$p -> $(curl -s -m 6 -u "$AU" -o /tmp/a_o -w %{http_code} 127.0.0.1:1111$p) $(head -c 160 /tmp/a_o)"; done
echo "== golden"; curl -s 127.0.0.1:8810/golden/result | python3 -c "
import json,sys;d=json.load(sys.stdin);print('принято',d['accepted'],'из',d['n'],d['share'])
for t in d['tasks']: print(' ',t['title'],t['role'],t['status'],'1й' if t['first_pass'] else '','возвр',t['returns'],round((t['finished'] or 0)-(t['started'] or 0)) if t['finished'] else '-')"
curl -s 127.0.0.1:8810/metrics; echo
echo "== /команда full10 + очередь: 12 задач, замер"
IDS=$(curl -s -m 10 -H 'Content-Type: application/json' -d '{"text":"/команда full10 напиши функцию sum_list(xs) и короткий README к ней"}' 127.0.0.1:8810/command); echo $IDS | head -c 300; echo
curl -s -m 8 127.0.0.1:8810/ | head -c 250; echo
for i in 1 2 3 4; do sleep 20; s=$(date +%s.%N); curl -s -m 100 127.0.0.1:8104/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","messages":[{"role":"user","content":"Привет"}],"max_tokens":16,"chat_template_kwargs":{"enable_thinking":false}}' >/dev/null; echo "chat latency under load $(echo "$(date +%s.%N) - $s" | bc) c; $(curl -s -m 5 127.0.0.1:8810/ | python3 -c "import json,sys;d=json.load(sys.stdin);print('running',d['running'],'queued',d['queued'])")"; done
curl -s 127.0.0.1:8104/slots | python3 -c "import json,sys;print('slots busy',[s['is_processing'] for s in json.load(sys.stdin)])"
