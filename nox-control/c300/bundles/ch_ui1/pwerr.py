import asyncio,json
from playwright.async_api import async_playwright
async def m():
    out={}
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for name,w,h,mob in (("1440",1440,900,0),("390",390,844,1)):
            c=await b.new_context(viewport={'width':w,'height':h},has_touch=bool(mob),is_mobile=bool(mob)); pg=await c.new_page(); bad=[]; errs=[]
            pg.on('response',lambda r: bad.append((r.status,r.url.replace('http://127.0.0.1:8091',''))) if r.status>=400 else None)
            pg.on('requestfailed',lambda r: bad.append(('RF',r.url.replace('http://127.0.0.1:8091','')[:90])))
            pg.on('pageerror',lambda e:errs.append(str(e)[:180])); pg.on('console',lambda msg: errs.append('C:'+msg.text[:180]) if msg.type=='error' else None)
            await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='domcontentloaded',timeout=30000); await pg.wait_for_timeout(9000)
            out[name]={'bad':sorted(set(bad))[:25],'errs':sorted(set(errs))[:15]}
            await c.close()
        await b.close()
    print(json.dumps(out,ensure_ascii=False,indent=1))
asyncio.run(m())
