import json,re
d=json.load(open('/workspace/nox/web/site/qa/audit.json'))
P='index creative settings system memory map knowledge widgets projects music news cinema mail calendar'.split()
src=d.get('pages') if isinstance(d.get('pages'),dict) else d
for k in P:
    v=src.get(k) or src.get(k+'.html')
    if not v: print(k,'-'); continue
    t=json.dumps(v,ensure_ascii=False); m=re.search(r'A/R/U=\[([^\]]*)\]',t); w=re.search(r'WOW ([0-9.]+)',t)
    print(k,v.get('ts') if isinstance(v,dict) else '', m.group(1) if m else 'A/R/U>=8?', 'WOW',w.group(1) if w else 'ok?', 'fails',len(v.get('fails',[])) if isinstance(v,dict) else '')
