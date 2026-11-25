tail -5 /tmp/r2_audit.log | cut -c1-300
pgrep -fa qa_audit | cut -c1-120
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/audit.json'))['settings']
print(r['ts'],r['ARU'],r['status'],r['vision_runs'],[ (k,v['status']) for k,v in r['items'].items() if v['status']!='ok'])
P
