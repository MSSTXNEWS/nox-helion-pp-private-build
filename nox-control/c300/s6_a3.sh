echo S4RUN:s6_a3
cd /workspace/nox/web/site
python3 - <<'PY'
import json
j=json.load(open('nav.json'))
print({k:(len(v) if hasattr(v,'__len__') else v) for k,v in j.items()})
s=json.dumps(j['groups'],ensure_ascii=False)
for p in 'games mail map nexus social calls contacts messenger notifications book-reader benchmark browser ai-learning advisors'.split():
    print(p,'GROUPS' if p+'.html' in s else '-', 'HIDDEN' if any(h['file']==p+'.html' for h in j['hidden']) else '-', 'SOON' if p+'.html' in json.dumps(j['soon']) else '-')
print(json.dumps(j['soon'],ensure_ascii=False)[:300]); print(type(j['pages']), j['pages'] if isinstance(j['pages'],int) else '')
for g in j['groups']:
    for it in g['items']:
        if it['file'] in ('map.html','nexus.html','notifications.html','benchmark.html'): print(json.dumps(it,ensure_ascii=False))
PY
python3 -c "
import json;j=json.load(open('data/live.json'));print(json.dumps(j,ensure_ascii=False)[:600])"
ls vendor/foliate-js/vendor | head; grep -n "customElements.define" vendor/foliate-js/view.js | head -3
