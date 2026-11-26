echo "C300: rv_d2"
N=/workspace/nox/state/rv
pgrep -f "rv_audit|rv_chat" | wc -l
cut -c1-1500 $N/d1chat.jsonl
python3 - <<'P'
import json
for l in open('/workspace/nox/state/rv/d1a.jsonl'):
    try:d=json.loads(l)
    except: print(l[:200]);continue
    d.pop('title',None)
    print(json.dumps(d,ensure_ascii=False)[:1300])
P
