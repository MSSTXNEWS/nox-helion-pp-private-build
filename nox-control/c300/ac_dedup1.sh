echo "C300: ac_dedup1"
D=/workspace/nox/tmp/dd; mkdir -p $D; V=/workspace/nox/venv/bin/python
$V -m pip install -q --no-deps --target $D datasketch 2>&1 | tail -1
ls -la --time-style=+%F /workspace/nox/distill_v2/items_base.jsonl /workspace/nox/distill_v2/paras.jsonl /workspace/nox/distill_v2/raw.jsonl /workspace/nox/distill_v2/decisions.jsonl 2>&1 | cut -c1-140
head -c 600 /workspace/nox/distill_v2/items_base.jsonl; echo
cat > $D/dd.py <<'PY'
import sys,json,re,time
sys.path.insert(0,'/workspace/nox/tmp/dd')
import numpy as np
from datasketch import MinHash, MinHashLSH
f='/workspace/nox/distill_v2/items_base.jsonl'
rows=[json.loads(l) for l in open(f)]
print('rows',len(rows),'keys',list(rows[0].keys())[:10])
def txt(r): return ' '.join(str(v) for k,v in r.items() if isinstance(v,str))[:4000]
t=time.time(); lsh=MinHashLSH(threshold=0.85,num_perm=64); dup=0; ex=[]
for i,r in enumerate(rows):
    w=re.findall(r'\w+',txt(r).lower()); sh={' '.join(w[j:j+5]) for j in range(max(1,len(w)-4))}
    m=MinHash(num_perm=64)
    for s in sh: m.update(s.encode())
    c=lsh.query(m)
    if c: dup+=1; ex.append((i,c[0]))
    else: lsh.insert(str(i),m)
print('near-dups(J>=0.85)',dup,'of',len(rows),'%.1f%%'%(100*dup/len(rows)),'sec %.0f'%(time.time()-t)); print(ex[:5])
PY
nice -n 19 taskset -c 4-7,20-23 timeout 200 $V -I $D/dd.py 2>&1 | tail -6
