echo "C300: k5_probe_3"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat /tmp/k2_qa.py | cut -c1-200 | head -20
$PY - <<'PY'
import asyncio
from playwright.async_api import async_playwright
V=['fabric/index.min.js','howler/howler.iife.js','embla-carousel/embla-carousel.iife.js','canvas-confetti/canvas-confetti.iife.js','typewriter-effect/typewriter-effect.iife.js','rive/rive.iife.js']
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();pg=await b.new_page()
    await pg.goto('http://127.0.0.1:8091/web/growth.html',wait_until='load');await pg.wait_for_timeout(1500)
    for v in V:
      r=await pg.evaluate("""async(v)=>{const a=new Set(Object.keys(window));await new Promise(r=>{const s=document.createElement('script');s.src='./vendor/'+v;s.onload=r;s.onerror=r;document.head.appendChild(s)});return Object.keys(window).filter(k=>!a.has(k)).join(',')}""",v)
      print(v,'->',r)
    print(await pg.evaluate("JSON.stringify({sl:!!customElements.get('sl-dialog'),tasks:localStorage.getItem('nox.tasks.v1')&&localStorage.getItem('nox.tasks.v1').length,keys:Object.keys(localStorage).slice(0,15)})"))
    for u in ['music','cinema','studio','photo','assistant','voice','chat','index']:
      g=await b.new_page();await g.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='load');await g.wait_for_timeout(2500)
      print(u,await g.evaluate("JSON.stringify({vid:document.querySelectorAll('video').length,img:document.querySelectorAll('#page img').length,cv:document.querySelectorAll('canvas').length,ta:document.querySelectorAll('textarea').length,inp:[...document.querySelectorAll('input,textarea')].slice(0,4).map(e=>e.id||e.name||e.className).join('|'),h1:(document.querySelector('h1')||{}).textContent})"))
    await b.close()
asyncio.run(m())
PY
