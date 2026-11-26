echo "C300: rv_r4"
N=/workspace/nox/state/rv
pgrep -f rv_audit | wc -l
python3 - <<'P'
import json
for f in ['p1','p2']:
    for l in open('/workspace/nox/state/rv/%s.jsonl'%f).read().splitlines():
        d=json.loads(l)
        print(d['page'][:-5],'FATAL '+d['fatal'][:60] if d.get('fatal') else '','e%s'%d.get('nerr'),[e[:60] for e in d.get('errs',[])][:4],'dead',d.get('ndead'),[x[:38] for x in d.get('dead',[])][:6],'bad',d.get('badlinks'),'clk',d.get('nclick'))
P
