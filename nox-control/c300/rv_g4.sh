echo "C300: rv_g4"
N=/workspace/nox/state/rv
pgrep -f "rv_audit|rv_chat" | wc -l
python3 - <<'P'
import json
for f in ['g2','g4']:
  for l in open('/workspace/nox/state/rv/%s.jsonl'%f):
    try:d=json.loads(l)
    except: continue
    d.pop('title',None); d['dead']=[x[:34] for x in d.get('dead',[])[:6]]; d['smallS']=[x[:44] for x in d.get('smallS',[])[:4]]; d['errs']=[x[:70] for x in d.get('errs',[])[:4]]; d.pop('contrastS',None); d.pop('imgBroken',None); d.pop('load_s',None)
    print(json.dumps(d,ensure_ascii=False)[:760])
P
cut -c1-420 $N/g3.jsonl
