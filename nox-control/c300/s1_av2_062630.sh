cd /tmp; cat > /tmp/av2.py <<'P'
import asyncio,base64,textwrap
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
        pg=await b.new_page(viewport={'width':1440,'height':900})
        await pg.goto('http://127.0.0.1:8091/web/chat.html'); await pg.wait_for_timeout(4000)
        await pg.click('#tgAvBtn'); await pg.wait_for_timeout(30000)
        await pg.evaluate("window.noxAvatar.test(1)"); await pg.wait_for_timeout(1500)
        el=await pg.query_selector('.tg-avp'); bb=await el.bounding_box(); print('BOX',bb)
        await pg.screenshot(path='/tmp/av2.jpg',type='jpeg',quality=60,clip={'x':bb['x'],'y':bb['y'],'width':bb['width'],'height':bb['height']})
        d=base64.b64encode(open('/tmp/av2.jpg','rb').read()).decode(); print(len(d))
        print('B64_av2_BEGIN'); print('\n'.join(textwrap.wrap(d,100))); print('B64_av2_END')
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/av2.py 2>&1
