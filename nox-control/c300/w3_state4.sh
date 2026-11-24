cd /workspace/nox/web/site
python3 - <<'P'
import json
d=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('chat','index','cinema','music'):
    v=d.get(k)
    if not v: print(k,'none'); continue
    print(k,v.get('ts'),v.get('status'),'wow',v.get('wow'),[ (f['item'][:25],str(f['detail'])[:260]) for f in v.get('fails',[])], v.get('fix'))
P
ls -la qa/rework
