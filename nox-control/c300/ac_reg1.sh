echo "C300: ac_reg1"
python3 - <<'PY'
import json
d=json.load(open('/workspace/nox/stewards/orch_registry.json'))
js=d.get('jobs',d) if isinstance(d,dict) else d
it=js.items() if isinstance(js,dict) else enumerate(js)
for k,j in it:
    if isinstance(j,dict): print(k, j.get('cpus'), j.get('port'), str(j.get('cmd') or j.get('args'))[:110])
print(type(d), list(d)[:6] if isinstance(d,dict) else '')
PY
