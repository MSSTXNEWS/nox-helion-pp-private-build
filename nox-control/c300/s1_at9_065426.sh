cd /tmp; cat > /tmp/at9.py <<'P'
import asyncio,base64,textwrap,sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
        for page in ['atlas.html','voice.html']:
            pg=await b.new_page(viewport={'width':1440,'height':900}); pend=set(); errs=[]
            pg.on('request',lambda r:pend.add(r.url)); pg.on('requestfinished',lambda r:pend.discard(r.url)); pg.on('requestfailed',lambda r:pend.discard(r.url))
            pg.on('pageerror',lambda e:errs.append(str(e)[:160]))
            try: await pg.goto('http://localhost:8091/web/'+page,wait_until='domcontentloaded',timeout=20000)
            except Exception as e: print('goto',e)
            await pg.wait_for_timeout(12000)
            print(page,'PENDING',[u[-70:] for u in pend][:6],'ERR',errs[:3])
            if page=='atlas.html':
                await pg.screenshot(path='/tmp/at9.jpg',type='jpeg',quality=50)
                d=base64.b64encode(open('/tmp/at9.jpg','rb').read()).decode(); print('B64_at9_BEGIN');print('\n'.join(textwrap.wrap(d,100)));print('B64_at9_END')
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/at9.py 2>&1 | tail -n +1
