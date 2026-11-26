echo "C300: rv_r1"
N=/workspace/nox/state/rv
ls $N | head -50 | tr '\n' ' '; echo
cat $N/b1.err 2>/dev/null | tail -5
python3 - <<'P'
import json
for l in open('/workspace/nox/state/rv/b1.jsonl'):
    try:d=json.loads(l)
    except: print('BAD',l[:200]);continue
    d.pop('title',None)
    print(json.dumps(d,ensure_ascii=False)[:1400])
P
