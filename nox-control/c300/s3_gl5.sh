S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== GL5"; sed -n 14,34p $S/nox-settings-tabs.js | cut -c1-520
echo "-- core"; sed -n 1488,1502p /workspace/nox/brain/BRAIN/nox_core.py | cut -c1-200
echo "-- about"; wc -c $S/about.html; head -c 2600 $S/about.html | cut -c1-400; echo ...; tail -c 900 $S/about.html
echo "-- reg notify"; $PY -c "
import json;r=json.load(open('$S/qa/registry.json'));print(type(r).__name__, list(r)[:3]);c=r['commands'] if isinstance(r,dict) and 'commands' in r else r
x=[v for v in (c if isinstance(c,list) else c.values()) if 'notify' in json.dumps(v)][0];print(json.dumps(x,ensure_ascii=False))
n=json.load(open('$S/nav.json'));print(type(n).__name__, list(n)[:6]);print(json.dumps(n,ensure_ascii=False)[:100])
"
grep -n "notify.test" /workspace/nox/web/pkg/server/nox_cmd.py | cut -c1-200 | head -5
