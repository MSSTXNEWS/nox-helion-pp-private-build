uptime | cut -c1-60
pgrep -af "qa_loop|qa_audit_loop" | cut -c1-80
tail -3 /workspace/nox/web/site/qa/history.log
tail -4 /workspace/nox/agent/out/qa_audit.log
python3 -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k,v in d.items(): print(k,v['status'],'WOW',v.get('wow'),'cycle',v.get('cycle'),v.get('ts'))"
