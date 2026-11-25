cat > /tmp/dbg.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch();pg=await (await b.new_context(viewport={'width':1440,'height':900})).new_page();errs=[]
    pg.on('pageerror',lambda e:errs.append('PE '+str(e)[:300]));pg.on('console',lambda m:errs.append('C '+m.text[:200]) if m.type in('error','warning') else None)
    await pg.goto('http://127.0.0.1:8091/web/creative.html',wait_until='load');await pg.wait_for_timeout(3000)
    await pg.evaluate("(()=>{var cv=NOXDZ.cv;var r=new fabric.Rect({left:100,top:100,width:200,height:100,fill:'#f00'});cv.add(r);cv.setActiveObject(r)})()")
    r=await pg.evaluate("(()=>{try{NOXDZ.AIACT['ai-sketch']();return 'called'}catch(e){return 'ERR '+e.stack}})()")
    await pg.wait_for_timeout(2000)
    print('OUT:',r,await pg.evaluate("[document.querySelectorAll('sl-dialog').length,[...document.querySelectorAll('sl-alert')].map(a=>a.textContent),document.querySelector('sl-dialog')&&document.querySelector('sl-dialog').open]"))
    print('OUT:',errs[:8])
    await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/dbg.py 2>&1 | tail -8 | cut -c1-900 | sed 's/^/OUT: /'
