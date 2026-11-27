echo "K1: ln_t12"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; M=127.0.0.1:18220
echo "== cleanup test facts"
curl -s -m10 -X POST $M/list -H 'Content-Type: application/json' -d '{"user":"owner","n":500,"q":"тестовый-"}' | python3 -c "
import sys,json
it=json.load(sys.stdin)['items']; print('items',len(it))
ids=[]
for i in it:
    s=json.dumps(i,ensure_ascii=False)
    f9917='9917' in s; f9918='9918' in s
    if f9917 or f9918: print('id',i.get('id'),'9917' if f9917 else '9918'); ids.append(i.get('id'))
open('/tmp/ln_ids','w').write(' '.join(str(x) for x in ids))"
for id in $(cat /tmp/ln_ids); do curl -s -m10 -X POST $M/forget -H 'Content-Type: application/json' -d "{\"user\":\"owner\",\"id\":$id}"; echo; done
echo "== inner errors last hour"
python3 - <<'PY'
import json,collections,datetime
now=datetime.datetime.utcnow(); cut=(now-datetime.timedelta(hours=1)).strftime('%H:%M:%S'); cur=now.strftime('%H:%M:%S')
c=collections.Counter(); tot=0
for l in open('/workspace/nox/agent/out/inner_loop.log',errors='ignore').read().splitlines()[-700:]:
    try: d=json.loads(l)
    except: continue
    t=d.get('t','')
    if t and cut<=t<=cur:
        tot+=1; c[(d.get('status'),d.get('error'))]+=1
print('window',cut,cur,'records',tot); print(dict(c))
PY
echo "== 8105"; curl -s -m6 -o /dev/null -w "8105 health %{http_code} %{time_total}s\n" 127.0.0.1:8105/health; curl -s -m6 127.0.0.1:8105/slots | head -c 100; echo
grep -n "тело мыслей" $N/tmp/liska_alive/inner_runner.py $N/brain/CON/nox_inner_loop.py 2>/dev/null | head -3 | cut -c1-200
