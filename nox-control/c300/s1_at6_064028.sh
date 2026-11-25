cd /workspace/nox/web/site; grep -o "fetch([^)]*events[^)]*)" index.html nox-*.js 2>/dev/null | head -4; python3 - <<'P'
import json
d=json.load(open('vendor/earth/data/earth-topo.json')); print(list(d.keys()), list(d['objects'].keys()), d.get('transform'), len(d['arcs']))
for k,v in d['objects'].items(): print(k, v.get('type'), len(v.get('geometries',[])))
P
