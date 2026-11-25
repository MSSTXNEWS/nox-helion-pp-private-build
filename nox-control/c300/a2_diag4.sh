echo "C300: a2_diag4"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/2d56a411548cad542360680bd232efc509f895e1/nox-control/c300; A=/workspace/nox/agents
echo "== procs"; ps -eo pid,etimes,args | grep -E "nox_agents|agents_guard|supervisor" | grep -v grep | cut -c1-150
echo "== llm timing"
for b in 8104 8141; do python3 - $b <<'P'
import sys,time,json,urllib.request
b=sys.argv[1]; t=time.time()
try:
    r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%s/v1/chat/completions'%b,data=json.dumps({'model':'x','messages':[{'role':'user','content':'скажи ок'}],'max_tokens':5}).encode(),headers={'Content-Type':'application/json'}),timeout=120).read()[:120]
except Exception as e: r=repr(e)[:100]
print(b,round(time.time()-t,1),'s',r)
P
done
echo "== guard log"; tail -5 $A/guard.log 2>/dev/null | cut -c1-200
echo "== restarts per task (steps requeue)"; python3 - <<'P'
import sqlite3
c=sqlite3.connect('/workspace/nox/agents/book.sqlite')
print(c.execute("select count(*) from steps where kind='requeue'").fetchone())
for r in c.execute("select task,ts,text from steps where kind in('requeue','error','escalate') order by id desc limit 6"): print(r)
print(c.execute("select ts from lease where k='disp1'").fetchone())
P
