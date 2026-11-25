cd /workspace/nox
sed -n 3,10p qa_audit.py | cut -c1-250
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/registry.json'))
print(list(r.keys()))
s=r.get('sections') or r.get('secs')
for k in list(r):
    if isinstance(r[k],dict) and 'cinema' in r[k]: print(k, json.dumps(r[k]['cinema'],ensure_ascii=False)[:600]); print(len(r[k]), [x for x in ['constructor','pdf','assistant','intents','models','scene','effects','widgets','about','integrations','glance','install'] if x in r[k]])
P
for p in constructor pdf assistant intents models scene effects widgets about integrations glance install; do ls web/site/$p.html; done
