echo "C300: rv_r3"
N=/workspace/nox/state/rv
pgrep -af "rv_audit|rv_chat" | cut -c1-90
ls -la $N/*.jsonl | awk '{print $5,$9}'
cat $N/chat2.jsonl | cut -c1-1500
python3 - <<'P'
import json
for f in ['a','b']:
    ls=open('/workspace/nox/state/rv/%s.jsonl'%f).read().splitlines()
    print('=====',f,len(ls))
    for l in ls:
        d=json.loads(l)
        d.pop('title',None); d['smallS']=[s[:40] for s in d.get('smallS',[])[:3]]; d['dead']=[s[:45] for s in d.get('dead',[])[:5]]
        if 'contrastS' in d: d['contrastS']=d['contrastS'][:2]
        d['errs']=[e[:70] for e in d.get('errs',[])[:4]]
        print(json.dumps(d,ensure_ascii=False)[:700])
P
