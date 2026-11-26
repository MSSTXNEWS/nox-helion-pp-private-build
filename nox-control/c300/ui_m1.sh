echo "C300: ui_m1"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/ui_m1.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('music','news'):
      c=await b.new_page(viewport={'width':1440,'height':900});await c.goto('http://127.0.0.1:8091/web/'+pg+'.html',wait_until='domcontentloaded');await c.wait_for_timeout(7000)
      print('BTN',pg,await c.evaluate("[...document.querySelectorAll('#app button,#app a,#app sl-button')].filter(e=>e.offsetWidth&&e.getBoundingClientRect().top<900).slice(0,25).map(e=>e.tagName+'#'+e.id+'.'+String(e.className).split(' ')[0]+'|'+(e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,24)).join(' ;; ')"),flush=True)
      print('UCTA',pg,await c.evaluate("document.querySelectorAll('.u-cta').length"),flush=True)
      await c.close()
    await b.close()
asyncio.run(m())
P
timeout 100 $PY /tmp/ui_m1.py
echo "== sw"; grep -c "x4" /workspace/nox/web/site/index.html; ls -la /workspace/nox/web/site/sw.js 2>&1; head -c 600 /workspace/nox/web/site/sw.js 2>&1
