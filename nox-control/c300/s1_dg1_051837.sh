cd /tmp; cat > /tmp/dg1.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w,h in((1440,900),(390,844)):
            pg=await b.new_page(viewport={'width':w,'height':h}); await pg.goto('http://127.0.0.1:8091/web/index.html'); await pg.wait_for_timeout(5000)
            r=await pg.evaluate("""()=>{const o=[];document.querySelectorAll('.hx-gs-item,#svc,#svc>*,.hx-extra,.hx-extra>*,#page').forEach(e=>{const b=e.getBoundingClientRect(),c=getComputedStyle(e);o.push([e.tagName+'.'+(e.className+'').slice(0,40),Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height),c.position,c.opacity,c.display,c.overflowY].join(' '))});return o.slice(0,40).join('\\n')}""")
            print(w);print(r)
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/dg1.py 2>&1 | cut -c1-200 | head -90
