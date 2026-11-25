python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('cinema','settings'):
    r=a[k]; print('==',k,r['ts'],r['ARU'],r['status'],r['vision_runs'])
    print({i:v['status'] for i,v in r['items'].items()})
    for f in r['fails']: print('FAIL',str(f['item'])[:60],'|',str(f['detail'])[:250])
    print('RAW',r['vision_raw'][:900].replace('\n',' '))
P
tail -4 /tmp/r2_audit.log | cut -c1-200
