cd /tmp; cat > /tmp/dg2.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={'width':1440,'height':900}); await pg.goto('http://127.0.0.1:8091/web/index.html'); await pg.wait_for_timeout(5000)
        r=await pg.evaluate("""()=>{const o=[];document.querySelectorAll('.hx-gs-item,.hx-svc>*,.hx-svc .card.svc,.hx-qa,.hx-qa a').forEach((e,i)=>{if(i>14&&!/svc/.test(e.className))return;const b=e.getBoundingClientRect(),c=getComputedStyle(e);o.push([e.tagName+'.'+(e.className+'').slice(0,30),Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height),c.position,c.opacity,c.display,c.visibility,c.overflowY].join(' '))});return o.slice(0,30).join('\\n')}""")
        print(r)
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/dg2.py 2>&1 | cut -c1-200 | head -40
