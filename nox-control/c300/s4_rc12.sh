echo S4RUN:s4_rc12
S=/workspace/nox/web/site
curl -s -m6 127.0.0.1:8091/svc/memos/ | grep -o '\(src\|href\)="[^"]*"' | head -6
for u in api/memos api/v1/memos memos.api.v1.MemoService/ListMemos api/status; do echo "-- $u $(curl -s -m6 -o /tmp/m.out -w '%{http_code}' -X GET 127.0.0.1:8091/svc/memos/$u)"; head -c 160 /tmp/m.out; echo; done
python3 - <<'P'
import json
d=json.load(open('/workspace/nox/web/site/nav.json'))
out=[]
def w(x):
    if isinstance(x,dict):
        h=x.get('href') or x.get('url')
        if h: out.append(h)
        for v in x.values(): w(v)
    elif isinstance(x,list):
        for v in x: w(v)
w(d); print(sorted(set(out)))
P
ls -la --time-style=+%m%d%H $S/*.html | awk '{print $6,$7}' | sed 's|/workspace/nox/web/site/||' | sort | head -90 | tr '\n' ' '
