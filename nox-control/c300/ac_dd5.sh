echo "C300: ac_dd5"
D=/workspace/nox/tmp/dd; V=/workspace/nox/venv/bin/python
F=/workspace/nox/ops/v5_knowledge_gpu_20261125/knowledge-rows.jsonl
wc -l $F; python3 -c "import json,collections;c=collections.Counter()
for l in open('$F'):
  r=json.loads(l);c[(r['kind'],r['key'].split(':')[1])]+=1
print(c.most_common(12))"
cat > $D/dd2.py <<'PY'
import sys,json,re,time
sys.path.insert(0,'/workspace/nox/tmp/dd')
from datasketch import MinHash, MinHashLSH
F=sys.argv[1]
def txt(r):
    if isinstance(r,dict): return ' '.join(txt(v) for v in r.values())
    if isinstance(r,list): return ' '.join(txt(v) for v in r)
    return r if isinstance(r,str) else ''
t=time.time(); lsh=MinHashLSH(threshold=0.85,num_perm=64); n=dup=0; ex=[]; exact=set(); ed=0
for i,l in enumerate(open(F)):
    try: r=json.loads(l)
    except Exception: continue
    ids=r.get('ids') or []; n+=1
    s=' '.join(map(str,ids[:1500]))
    h=hash(s)
    if h in exact: ed+=1
    exact.add(h)
    w=s.split(); sh={' '.join(w[j:j+8]) for j in range(max(1,len(w)-7))}
    m=MinHash(num_perm=64)
    for x in sh: m.update(x.encode())
    c=lsh.query(m)
    if c: dup+=1; ex.append((i,int(c[0])))
    else: lsh.insert(str(i),m)
    if time.time()-t>230: print('TIME CUT at',n); break
print('rows',n,'exact-dups',ed,'near-dups(J>=0.85,5-gram)',dup,'%.1f%%'%(100*dup/max(n,1)),'sec %.0f'%(time.time()-t)); print(ex[:8])
PY
nice -n 19 taskset -c 4-7,20-23 timeout 260 $V -I $D/dd2.py $F 2>&1 | tail -5 | cut -c1-300
