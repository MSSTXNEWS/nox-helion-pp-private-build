cd /workspace/nox/web/site
python3 - <<'P'
import json,os
d=json.load(open('nav.json'))
for g in d.get('groups',[]):
    print('##',g.get('title') or g.get('name') or g.get('id'),':',', '.join((p.get('title') or p.get('name') or '?')+'='+(p.get('href') or p.get('url') or p.get('page') or '') for p in g.get('items',g.get('pages',[]))))
print('PAGES', ', '.join((p.get('title') or '?')+'='+(p.get('href') or p.get('url') or '') for p in d.get('pages',[])) if isinstance(d.get('pages'),list) else str(d.get('pages'))[:1500])
print('SOON', str(d.get('soon'))[:1200])
P
ls *.html | wc -l; ls *.html | tr '\n' ' '
echo; cat /workspace/nox/web/pkg/server/svc_registry.json 2>/dev/null | head -c 800
