echo "C300: w_r4"
N=/workspace/nox
wc -l $N/agent/out/w_matrix.jsonl; tail -1 $N/agent/out/w_matrix.jsonl | cut -c1-80
python3 - <<'P'
import json,collections
rows=[]
for l in open('/workspace/nox/agent/out/w_matrix.jsonl'):
    try: rows.append(json.loads(l))
    except Exception: pass
g=collections.defaultdict(list)
for r in rows:
    if 'o' in r: g[(r['page'],r['vp'])].append(r)
for k,v in g.items():
    cc=[r['cc'] for r in v]; base=v[0]['cc']
    ap=sum(1 for r in v if r['c'][0] and r['o']['world']==r['c'][0] or r['c'][1] and r['o']['color']==r['c'][1] or r['c'][2] and r['o']['btn']==r['c'][2])
    rgbs=len(set(r['o']['rgb'] for r in v)); bgs=len(set(str(r['o']['b']) for r in v)); hs=sum(1 for r in v if r['o']['hs'])
    print(k,'n',len(v),'applied',ap,'distinct_rgb',rgbs,'distinct_btnstyle',bgs,'cc min/max',min(cc),max(cc),'hscroll',hs,'theme',v[0]['o']['theme'])
    worst=max(v,key=lambda r:r['cc']);print('   worst',worst['c'],worst['cc'],worst['ex'][:1])
errs=[r for r in rows if 'err' in r];print('errs',len(errs),errs[:2])
P
