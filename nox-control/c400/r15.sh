#!/bin/bash
echo "IMP rc: $(cat /root/nox/state/c400_imp.rc 2>/dev/null || echo running); proc: $(pgrep -f import_cli | wc -l)"
python3 -I - <<'PY'
import sqlite3,json,urllib.request,random
c=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True)
rows=c.execute("select id,text from mem_facts where status='active'").fetchall(); random.seed(400); smp=random.sample(rows,30)
def api(o,path='/api'):
    for p in (path,'/memory/api'):
        try:
            r=urllib.request.Request('http://127.0.0.1:8095'+p,json.dumps(o).encode(),{'Content-Type':'application/json'}); return json.loads(urllib.request.urlopen(r,timeout=20).read())
        except Exception as e: err=e
    return {'err':str(err)[:80]}
def walk(x,out):
    if isinstance(x,dict):
        if 'text' in x: out.append(x)
        for v in x.values(): walk(v,out)
    elif isinstance(x,list):
        for v in x: walk(v,out)
ok=found=0; bad=[]
for i,t in smp:
    r=api({'op':'search','query':t[:90],'k':8}); L=[]; walk(r,L)
    hit=[h for h in L if h.get('text')==t]
    if hit: ok+=1
    elif any(h.get('text') and h['text'][:60]==t[:60] for h in L): bad.append(i)
print('search exact-match',ok,'of',len(smp),'; prefix-only mismatch ids',bad[:5]); print('sample resp keys',list(r.keys())[:6])
r=api({'op':'list'}); print('list ok',r.get('ok'),len(r.get('facts',[])))
r=api({'op':'core','budget_tokens':200}); print('core',str(r)[:160])
print('health',api({'op':'x'}))
PY
