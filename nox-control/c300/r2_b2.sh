cd /workspace/nox/web/site
python3 - <<'P'
import json
a=json.load(open('qa/audit.json'))
r=a['settings']; print(list(r.keys()))
for k,v in r.items():
    if k not in('fails','vendor_used'): print(k, json.dumps(v,ensure_ascii=False)[:300])
print('ITEMS',json.dumps(r.get('items'),ensure_ascii=False)[:800])
P
ls *.json data/nav.json 2>/dev/null | head; python3 -c "
import json;d=json.load(open('/workspace/nox/web/site/nav.json'));print(json.dumps(d,ensure_ascii=False)[:1500])" 2>&1 | head -20
grep -n "ИИ" /workspace/nox/../nox/web/site/qa/CHECKLIST.md /workspace/nox/nox-control/c300/CHECKLIST.md 2>/dev/null | head
tail -3 /tmp/r2_audit.log
