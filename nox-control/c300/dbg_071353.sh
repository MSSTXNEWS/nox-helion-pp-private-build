cat > /tmp/d.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
        pg=await b.new_page(viewport={'width':1440,'height':900}); await pg.goto('http://localhost:8091/web/atlas.html',wait_until='domcontentloaded'); await pg.wait_for_timeout(9000)
        print('DBG',await pg.evaluate("[window.__atCoast,window.__atErr]"))
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/d.py 2>&1 | tail -3
