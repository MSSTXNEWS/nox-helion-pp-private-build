echo "C300: a2_collect3"
curl -s -m10 127.0.0.1:8810/tasks | python3 -c "
import json,sys,urllib.request
for t in json.load(sys.stdin)[:30]:
    if t['title'] not in ('c1-slugify','c2-readme','c3-restart'): continue
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8810/task/'+t['id'],timeout=10))
    st=d['steps']
    print(t['id'],t['title'],t['status'],'brief',sum(s['kind']=='brief' for s in st),'coach',[s['text'][:80] for s in st if s['kind']=='coach' and 'прогресса' not in s['text']],'fallback',sum(s['kind']=='fallback' for s in st),'lessons',sum(s['kind']=='lesson' for s in st))
    print('   last',[(s['kind'],s['text'][:60]) for s in st[-4:]]); print('   artifacts',[a['path'] for a in (d.get('result') or {}).get('artifacts',[])])
"
curl -s -m5 127.0.0.1:8810/metrics | head -c 400; echo; curl -s -m5 127.0.0.1:8810/inspect; echo
curl -s -m5 127.0.0.1:8810/lessons | head -c 800; echo
