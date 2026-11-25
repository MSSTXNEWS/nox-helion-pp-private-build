grep -n "^DONE\|owner WOW\|rework WOW\|accepted WOW" /tmp/r2_audit.log | cut -c1-120
python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('photo','atlas','index','news','chat','finance','cinema'):
    r=a[k]; print(k,r['ts'],r['ARU'],r['wow'],[i for i,v in r['items'].items() if v['status']=='rework'])
P
date
