W=/workspace/nox; ST=$W/state
curl -s 127.0.0.1:8810/golden/result | python3 -c "
import json,sys;d=json.load(sys.stdin);print('GOLDEN принято',d['accepted'],'из',d['n'],d['share'])
for t in d['tasks']: print(' ',t['title'],t['role'],t['status'],'1й' if t['first_pass'] else '', 'возвр',t['returns'],round((t['finished'] or 0)-(t['started'] or 0)))"
curl -s 127.0.0.1:8810/metrics; echo
$W/agents/venv/bin/python - <<'P'
import sqlite3;c=sqlite3.connect('/workspace/nox/agents/book.sqlite')
for r in c.execute("select task,kind,role,substr(text,1,150) from steps where kind in ('review','escalate','trainer','warn','error') order by id desc limit 24"):print(r)
P
echo "== chat latency"; for i in 1 2; do s=$(date +%s.%N); curl -s -m 100 127.0.0.1:8104/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","messages":[{"role":"user","content":"Скажи привет"}],"max_tokens":20,"chat_template_kwargs":{"enable_thinking":false}}' >/dev/null; echo "$(echo "$(date +%s.%N) - $s" | bc) c"; done; uptime
echo "== как чат/сайт зовёт svc"; for u in 8090 8091 8094 8095; do echo "$u svc/agents -> $(curl -s -m 4 -o /dev/null -w %{http_code} 127.0.0.1:$u/svc/agents/)"; done
grep -n "svc_registry\|/svc/" $W/web/pkg/server/web_server.py | head -8 | cut -c1-200
echo "== registry cmd"; head -c 700 $W/web/site/qa/registry.json; echo; sed -n 44,69p $W/web/pkg/server/nox_cmd.py | cut -c1-200
echo "== chat команды (слэш)"; grep -rnE '"/запомни|/память|/учить' $W/web/pkg/server/*.py $W/living/*.py 2>/dev/null | head -6 | cut -c1-220; ls $W/living 2>/dev/null | head
echo "== ЧЕРВИ"; ps -eo pid,etimes,args | grep -iE 'worm|nexus|hunter|drive_bridge|rclone|crawl|scout|dream|idea' | grep -v grep | cut -c1-230 | head -14
find $W -maxdepth 3 \( -iname '*worm*' -o -iname '*nexus*' -o -iname '*hunt*' -o -iname '*dream*' \) -not -path '*/node_modules/*' -not -path '*/models/*' -not -path '*/venv*' 2>/dev/null | head -14
ss -ltnp 2>/dev/null | grep 18765 | awk '{print $4,$6}'; curl -s -m 4 127.0.0.1:18765/ | head -c 200; echo
