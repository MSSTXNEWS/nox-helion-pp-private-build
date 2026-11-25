echo "C300: u_diag7"
S=/workspace/nox/web/site; cd $S
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
cat > /tmp/u_f2.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('finance','chat'):
      c=await b.new_page(viewport={'width':1440,'height':900})
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      print(pg,await c.evaluate("""()=>{const f=document.querySelector('.nmc-fab');if(!f)return 'nofab';const b=f.getBoundingClientRect();const t=document.elementFromPoint(b.left+b.width/2,b.top+b.height/2);return [b.left|0,b.top|0,b.width|0,b.height|0,getComputedStyle(f).bottom,getComputedStyle(f).display,t?t.tagName+'#'+t.id+'.'+String(t.className).slice(0,30)+' in '+((t.closest('[id]')||{}).id):null,innerHeight]}"""))
      try:
        await c.click('.nmc-fab',timeout=2500);print('clicked')
      except Exception as e: print('ERR',str(e)[:400])
      await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 80 /workspace/nox/venv/bin/python /tmp/u_f2.py
cat /tmp/u_qaa_prog.txt 2>/dev/null
