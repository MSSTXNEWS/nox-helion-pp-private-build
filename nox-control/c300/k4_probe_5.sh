echo "C300: k4_probe_5"
S=/workspace/nox/web/site; cd $S
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
$PY - <<'PY'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    pg=await b.new_page(viewport={'width':1440,'height':900})
    await pg.goto('http://127.0.0.1:8091/web/news.html');await pg.wait_for_timeout(3500)
    print(await pg.evaluate("(()=>{const b=document.getElementById('k4-cu');const cs=getComputedStyle(b);const c=b.querySelector('button');const ccs=getComputedStyle(c);return JSON.stringify({bh:b.offsetHeight,disp:cs.display,vis:cs.visibility,ch:c.offsetHeight,cdisp:ccs.display,cw:c.offsetWidth,par:b.parentNode.className,sib:[...b.parentNode.children].map(x=>x.tagName+'#'+x.id+'.'+x.className)})})()"))
    pg2=await b.new_page(viewport={'width':1440,'height':900})
    await pg2.goto('http://127.0.0.1:8091/web/index.html');await pg2.wait_for_timeout(3000)
    print(await pg2.evaluate("(()=>{const g=document.getElementById('svc');return JSON.stringify({par:g.parentNode.tagName+'.'+g.parentNode.className,sib:[...g.parentNode.children].map(x=>x.tagName+'#'+x.id+'.'+x.className).slice(0,8)})})()"))
    pg3=await b.new_page(viewport={'width':1440,'height':900})
    await pg3.goto('http://127.0.0.1:8091/web/atlas.html');await pg3.wait_for_timeout(3000)
    print(await pg3.evaluate("[!!customElements.get('sl-dialog'),!!customElements.get('sl-button'),!!customElements.get('sl-drawer'),!!customElements.get('sl-input')]"))
    for u in ('effects','photo','system'):
      pg4=await b.new_page(viewport={'width':1440,'height':900})
      await pg4.goto('http://127.0.0.1:8091/web/'+u+'.html');await pg4.wait_for_timeout(2500)
      print(u,await pg4.evaluate("[!!customElements.get('sl-dialog'),document.querySelector('#page .wrap')?1:0]"))
    await b.close()
asyncio.run(m())
PY
