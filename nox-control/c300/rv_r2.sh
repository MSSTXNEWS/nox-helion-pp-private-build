echo "C300: rv_r2"
N=/workspace/nox/state/rv
tail -3 $N/*.err 2>/dev/null | cut -c1-200
python3 - <<'P'
import json,glob
for f in ['b1','chat','a','b']:
    try: ls=open('/workspace/nox/state/rv/%s.jsonl'%f).read().splitlines()
    except: continue
    print('=====',f,len(ls))
    for l in ls:
        try:d=json.loads(l)
        except: print('BAD');continue
        if f=='b1' and d.get('page')=='index.html': continue
        d.pop('title',None); d['smallS']=[s[:46] for s in d.get('smallS',[])[:5]]; d['dead']=[s[:50] for s in d.get('dead',[])[:6]]
        if 'contrastS' in d: d['contrastS']=d['contrastS'][:3]
        print(json.dumps(d,ensure_ascii=False)[:1100])
P
