cd /workspace/nox/web/site
python3 - <<'P'
import json
d=json.load(open('qa/audit.json'))
for k,v in d.items(): print(k,v.get('ts'),v.get('status'),'wow',v.get('wow'),'cycle',v.get('cycle'),len(v.get('fails',[])))
P
ls qa/rework; wc -l /workspace/nox/qa_audit.py; grep -n "screenshot\|goto\|def \|PAGES\|pages" /workspace/nox/qa_audit.py | head -40
grep -n "Справка\|СПРАВКА" nox-*.js nox-*.css | cut -c1-220 | head
