python3 - <<'P'
import json;p='/workspace/nox/web/pkg/server/svc_registry.json';d=json.load(open(p))
d['invoke']={'port':9090,'mode':'strip','title':'InvokeAI','alias':['/ws/','/api/v1/','/api/v2/','/openapi.json'],'note':'Холст InvokeAI 6.9 (SD1.5 DreamShaper 8)'}
json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
P
ls -la /workspace/nox/models/invoke | tail -2
curl -s -m60 -X POST "localhost:9090/api/v2/models/install?source=%2Fworkspace%2Fnox%2Fmodels%2Finvoke%2FDreamShaper_8_pruned.safetensors&inplace=true" -H 'Content-Type: application/json' -d '{}' | head -c 300; echo
sleep 20; curl -s -m10 "localhost:9090/api/v2/models/?model_type=main" | head -c 400; echo
cat > /tmp/iv.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    bad=[]; pg.on('requestfailed',lambda r:bad.append('F '+r.url[-70:])); pg.on('response',lambda r:bad.append('%d %s'%(r.status,r.url[-70:])) if r.status>=400 else None)
    pg.on('console',lambda m:bad.append('C '+m.text[:100]) if m.type=='error' else None)
    pg.goto('http://localhost:8091/svc/invoke/',wait_until='load'); pg.wait_for_timeout(9000)
    print(pg.title(), pg.url); print('\n'.join(bad[:12]))
    pg.screenshot(path='/tmp/iv.png'); b.close()
P
/workspace/nox/venv/bin/python /tmp/iv.py 2>&1 | tail -15 | cut -c1-200
