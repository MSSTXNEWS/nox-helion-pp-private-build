echo "C300: rv_f2"
N=/workspace/nox/state/rv
pgrep -f "rv_audit|rv_chat" | wc -l
cut -c1-1500 $N/f1chat.jsonl
python3 - <<'P'
import json
for l in open('/workspace/nox/state/rv/f1a.jsonl'):
    try:d=json.loads(l)
    except: print(l[:200]);continue
    d.pop('title',None); d['dead']=d.get('dead',[])[:8]
    print(json.dumps(d,ensure_ascii=False)[:1300])
P
