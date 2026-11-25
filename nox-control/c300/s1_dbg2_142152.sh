cat > /tmp/d.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={'width':1440,'height':900}); errs=[]
        pg.on('pageerror',lambda e:errs.append((str(e)[:120],(getattr(e,'stack','') or '')[:300])))
        pg.on('console',lambda m:errs.append(('C',m.text[:150])) if m.type=='error' else None)
        await pg.goto('http://localhost:8091/web/assistant.html',wait_until='domcontentloaded'); await pg.wait_for_timeout(9000)
        for e in errs: print('DBG',e)
        print('DBG term',await pg.inner_text('#term')); 
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/d.py 2>&1 | tail -12
