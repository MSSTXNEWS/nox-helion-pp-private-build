echo "C300: u_probe_p7"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/u_pp.py <<'PEOF'
import asyncio,json,urllib.request
from playwright.async_api import async_playwright
B='http://127.0.0.1:8091'
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();c=await b.new_page()
    await c.goto(B+'/web/settings.html',wait_until='domcontentloaded');await c.wait_for_timeout(4000)
    await c.evaluate("NOXNote.open()");await c.wait_for_timeout(600)
    print('inputs',await c.evaluate("[...document.querySelectorAll('#u-pad input')].map(i=>i.className+'|'+i.placeholder)"))
    await c.fill('.up-p input:not(.up-q)','ПроектQA');await c.wait_for_timeout(300)
    print('LS',await c.evaluate("localStorage.getItem('nox.pad.v1')"))
    await c.evaluate("NOXNote.add('U_QA_PAD7 текст',{to:'pad'})");await c.wait_for_timeout(4500)
    print('LS2',await c.evaluate("localStorage.getItem('nox.pad.v1')"))
    print('REMOTE',[n['text'][:40] for n in json.load(urllib.request.urlopen(B+'/api/notes'))['notes'] if n['id'].startswith('pad-')])
    n=json.load(urllib.request.urlopen(B+'/api/notes'))['notes'];n=[x for x in n if 'U_QA_PAD' not in x['text']]
    urllib.request.urlopen(urllib.request.Request(B+'/api/notes',json.dumps({'notes':n}).encode(),{'Content-Type':'application/json'}))
    await b.close()
asyncio.run(m())
PEOF
timeout 60 $PY /tmp/u_pp.py 2>&1 | cut -c1-400
