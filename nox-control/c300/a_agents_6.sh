W=/workspace/nox; ST=$W/state
echo "== ЧЕРВИ / NEXUS recon"
ps -eo pid,etimes,args | grep -iE 'worm|nexus|hunter|predator|drive_bridge|gdrive|rclone|18765|crawl|scout|forager|hf_scan|c07' | grep -v grep | cut -c1-260
echo "-- cron/systemd"; crontab -l 2>/dev/null | grep -v '^#' | head; ls /etc/cron.d 2>/dev/null | head
echo "-- start_*.sh refs"; grep -lEi 'worm|nexus|черв' $W/svc/*.sh $W/*.sh 2>/dev/null | head
find $W -maxdepth 3 \( -iname '*worm*' -o -iname '*nexus*' -o -iname '*hunt*' \) -not -path '*/node_modules/*' -not -path '*/models/*' 2>/dev/null | head -20
echo "-- port 18765"; curl -s -m 4 127.0.0.1:18765/ | head -c 300; echo; ss -ltnp 2>/dev/null | grep -E '18765' | awk '{print $4,$6}'
ls $ST | grep -iE 'worm|nexus|hunt|drive|hunger|rag' | head
echo "== GOLDEN запуск (10 задач)"
J=$(curl -s -m 10 -X POST 127.0.0.1:8810/golden); echo $J
T0=$(date +%s)
echo "== chat latency probe (слот чата 8104, 20 токенов) во время нагрузки"
probe(){ s=$(date +%s.%N); curl -s -m 120 127.0.0.1:8104/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","messages":[{"role":"user","content":"Скажи привет одним словом"}],"max_tokens":20,"chat_template_kwargs":{"enable_thinking":false}}' >/dev/null; e=$(date +%s.%N); echo "chat latency $(echo "$e - $s" | bc) c (+$(( $(date +%s)-T0 ))s)"; }
for k in 1 2 3 4 5 6 7 8 9 10 11 12 13 14; do
  sleep 35; probe
  R=$(curl -s 127.0.0.1:8810/golden/result); echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['accepted'],'/',d['n'],[t['status'][:4] for t in d['tasks']])"
  echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);sys.exit(0 if all(t['status'] in ('done','needs_owner','failed') for t in d['tasks']) and d['n']==10 else 1)" && break
done
echo "== итог"; curl -s 127.0.0.1:8810/golden/result | python3 -c "
import json,sys;d=json.load(sys.stdin);print('принято',d['accepted'],'из',d['n'],d['share'])
for t in d['tasks']: print(' ',t['title'],t['role'],t['status'],'1й раз' if t['first_pass'] else '', 'возвр',t['returns'],round((t['finished'] or 0)-(t['started'] or 0)))"
curl -s 127.0.0.1:8810/metrics; echo
sqlite3 $W/agents/book.sqlite "select task,kind,substr(text,1,140) from steps where kind in ('review','escalate','trainer') order by id desc limit 24" 2>/dev/null || $W/agents/venv/bin/python -c "
import sqlite3;c=sqlite3.connect('$W/agents/book.sqlite')
for r in c.execute(\"select task,kind,substr(text,1,150) from steps where kind in ('review','escalate','trainer') order by id desc limit 24\"):print(r)"
curl -s -m 5 127.0.0.1:8104/slots | python3 -c "import json,sys;print([s['is_processing'] for s in json.load(sys.stdin)])"
uptime
