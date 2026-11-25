echo "C300: a2_diag1"
A=/workspace/nox/agents
python3 - <<'P'
import sqlite3,time,collections
c=sqlite3.connect('/workspace/nox/agents/book.sqlite'); c.row_factory=sqlite3.Row
rows=c.execute('select id,title,goal,role,team,project,status,created,started,finished,returns,restarts,first_pass from tasks order by created').fetchall()
print('total',len(rows),collections.Counter(r['status'] for r in rows))
print('cols',[k for k in rows[0].keys()])
g=collections.defaultdict(list)
for r in rows: g[(r['title'][:30])].append(r)
for k,v in sorted(g.items(),key=lambda x:-len(x[1]))[:25]:
    print(len(v),k,'|',collections.Counter(x['status'] for x in v),'restarts',sum(x['restarts'] or 0 for x in v),'team',v[0]['team'],'proj',v[0]['project'])
print('top restarts',[(r['id'],r['title'][:20],r['restarts']) for r in sorted(rows,key=lambda r:-(r['restarts'] or 0))[:8]])
now=time.time()
print('oldest running',[(r['id'],r['title'][:20],int((now-r['created'])/60)) for r in rows if r['status'] in('running','queued')][:6])
for r in c.execute("select task,kind,count(*) n from steps group by task,kind having kind='coach' and n>=2 order by n desc limit 5"): print('coachloop',dict(r))
P
curl -s -m5 127.0.0.1:8810/health; echo; curl -s -m5 127.0.0.1:8104/slots 2>/dev/null | head -c 300; echo
tail -5 $A/service.log | cut -c1-200; grep -c "ReadTimeout\|timeout" $A/service.log
