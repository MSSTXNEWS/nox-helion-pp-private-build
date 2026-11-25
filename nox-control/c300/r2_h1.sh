date; df -h /workspace | tail -1
pgrep -fa "r2_queue|qa_audit.py" | cut -c1-110
grep "^DONE" /tmp/r2_audit.log | tail -8
python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k,r in sorted(a.items(), key=lambda x:x[1].get('ts','')):
    if r.get('ts','')>'2026-11-25 13:40': print(k,r['ts'],r['ARU'],[i for i,v in r['items'].items() if v['status']=='rework' and i!='20'])
P
