cat > /tmp/d.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
        pg=await b.new_page(viewport={'width':3840,'height':2160}); await pg.goto('http://localhost:8091/web/atlas.html',wait_until='domcontentloaded'); await pg.wait_for_timeout(9000)
        print('DBG',await pg.evaluate("""()=>['html','body','#page','.at-stage','.at-layers','.at-legend','.at-card','#atGlobe'].map(s=>{const e=document.querySelector(s);if(!e)return s+' none';const b=e.getBoundingClientRect(),c=getComputedStyle(e);return s+' '+[Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height),'zoom='+c.zoom,c.position,'tr='+c.transform.slice(0,30)].join(' ')}).join('\\n')"""))
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/d.py 2>&1 | tail -12
