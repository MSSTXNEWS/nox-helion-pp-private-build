import asyncio,json
from playwright.async_api import async_playwright
async def run(b,block):
    c=await b.new_context(viewport={'width':1440,'height':900},service_workers='block' if block else 'allow'); pg=await c.new_page(); rf=[]
    pg.on('requestfailed',lambda r: rf.append((r.url.replace('http://127.0.0.1:8091','')[-34:],str(r.failure)[:40])))
    await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='domcontentloaded',timeout=30000); await pg.wait_for_timeout(6000)
    rf.clear()
    await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='domcontentloaded',timeout=30000); await pg.wait_for_timeout(9000)
    st=await pg.evaluate("[typeof window.NOXNote,typeof window.__rqRender,typeof window.K8meta,!!navigator.serviceWorker.controller,!!document.querySelector('.cw-bar')].join(',')")
    await c.close(); return {'block':block,'state':st,'rf':len(rf),'sample':rf[:5]}
async def m():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for blk in (False,True): print(json.dumps(await run(b,blk),ensure_ascii=False))
        await b.close()
asyncio.run(m())
