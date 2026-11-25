echo "C300: ux_get_c2"
python3 - <<'PY'
import json,re
d=json.load(open('/workspace/nox/agent/out/ux_c_raw.json'))
for k,r in sorted(d.items()):
    if not k.startswith('after_'): continue
    t=json.dumps(r,ensure_ascii=False)
    c=r.get('critique') or {}
    print(k, str(c.get('issues') or '')[:380], '|FIX', str(c.get('fixes') or r.get('text') or t)[:380])
PY
