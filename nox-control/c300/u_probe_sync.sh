echo "C300: u_probe_sync"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/u_ps.py <<'PEOF'
import asyncio,json,urllib.request
from playwright.async_api import async_playwright
B='http://127.0.0.1:8091'
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();c=await b.new_page()
    c.on('pageerror',lambda e:print('PE',str(e)[:150]));c.on('console',lambda m:print('CON',m.text[:150]) if m.type=='error' else None)
    c.on('request',lambda r:print('REQ',r.method,r.url[-40:],(r.post_data or '')[:100]) if '/api/notes' in r.url else None)
    c.on('response',lambda r:print('RES',r.status,r.url[-30:]) if '/api/notes' in r.url else None)
    await c.goto(B+'/web/settings.html',wait_until='domcontentloaded');await c.wait_for_timeout(5000)
    print('ver',await c.evaluate("[...document.scripts].filter(s=>/pad/.test(s.src)).map(s=>s.src)"))
    await c.evaluate("NOXNote.add('U_QA_PAD2 sync',{to:'pad'})");await c.wait_for_timeout(5000)
    print([n['id'] for n in json.load(urllib.request.urlopen(B+'/api/notes'))['notes']])
    n=json.load(urllib.request.urlopen(B+'/api/notes'))['notes'];n=[x for x in n if 'U_QA_PAD' not in x['text']]
    urllib.request.urlopen(urllib.request.Request(B+'/api/notes',json.dumps({'notes':n}).encode(),{'Content-Type':'application/json'}))
    await b.close()
asyncio.run(m())
PEOF
timeout 60 $PY /tmp/u_ps.py 2>&1 | cut -c1-300
