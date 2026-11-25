echo "C300: u_diag9"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/u_f4.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();c=await b.new_page(viewport={'width':1440,'height':900})
    await c.goto('http://127.0.0.1:8091/web/finance.html',wait_until='domcontentloaded');await c.wait_for_timeout(5000)
    print(await c.evaluate("""()=>{const chain=e=>{const o=[];while(e&&e!==document.documentElement){const s=getComputedStyle(e);o.push(e.tagName+'#'+e.id+'.'+String(e.className).slice(0,20)+' pos:'+s.position+' z:'+s.zIndex+' tf:'+(s.transform!=='none'?1:0));e=e.parentElement}return o};const a=document.querySelector('.nai-btn'),f=document.querySelector('.nmc-fab');const ra=a.getBoundingClientRect();return {nai:[ra.left|0,ra.top|0,ra.width|0,ra.height|0],naiChain:chain(a),fabChain:chain(f),has:CSS.supports('selector(:has(a))'),m:matchMedia('(min-width:769px)').matches,body:document.body.matches('body:has(.nai-btn)'),fabMatch:f.matches('body:has(.nai-btn) .nmc-fab')}}"""))
    await b.close()
asyncio.run(m())
PEOF
timeout 60 $PY /tmp/u_f4.py
O=/workspace/nox/agent/out; cat $O/u_qaa_prog.txt 2>/dev/null; ls $O | grep u_qaa
