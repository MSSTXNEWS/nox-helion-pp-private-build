echo "C300: a2_prio1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; A=/workspace/nox/agents
cp $A/book.sqlite $A/book.sqlite.bak_a2_prio
curl -fsSL "$R/nox_agents.py?$(date +%s)" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 12
python3 - <<'P'
import sqlite3,collections
c=sqlite3.connect('/workspace/nox/agents/book.sqlite'); c.row_factory=sqlite3.Row
rows=c.execute("select id,title,goal,status,created from tasks where status in('queued','running') order by created").fetchall()
seen={}; cancel=[]
for r in rows:
    k=(r['title'],r['goal'][:80])
    if k in seen: cancel.append(seen[k]); 
    seen[k]=r['id']
byt={r['id']:r for r in rows}
for r in rows:
    if r['title'] in ('hello-func','readme','deploy-script'): cancel.append(r['id'])   # дубли c1/c2/c3
cancel=list(dict.fromkeys(cancel))
for i in cancel: c.execute("update tasks set status='cancelled',finished=strftime('%s','now') where id=?",(i,))
c.execute("update tasks set prio=10,project='chat' where title in ('c1-slugify','c2-readme','c3-restart')")
c.execute("update tasks set prio=-5 where project='golden'")
c.commit(); print('cancelled',len(cancel),[byt[i]['title'] for i in cancel])
P
sleep 150
curl -s -m10 127.0.0.1:8810/board | python3 -c "
import json,sys
for k,v in json.load(sys.stdin).items():
    for c in v[:8]: print(k,c['id'],c['title'][:22],c['stage'],c['pct'],c['blocker'][:50],'|',c['doing'][:50])
"
curl -s -m5 127.0.0.1:8810/metrics | head -c 300; echo
