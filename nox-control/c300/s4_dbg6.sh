echo S4RUN:s4_dbg6
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
cat > /tmp/s4_dbg6.py <<'PYEOF'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        for h in (900,1500):
            pg=await b.new_page(viewport={"width":1440,"height":h})
            await pg.goto("http://127.0.0.1:8091/web/consciousness.html",wait_until="load"); await pg.wait_for_timeout(7000)
            print(h, await pg.evaluate("""()=>{const o=[];document.querySelectorAll('body *').forEach(e=>{const s=getComputedStyle(e);if((s.position==='fixed'||s.position==='absolute')&&e.getBoundingClientRect().width>innerWidth*.8&&e.getBoundingClientRect().height>innerHeight*.5){o.push([e.tagName,e.id,String(e.className).slice(0,40),s.zIndex,s.backgroundColor.slice(0,30),s.opacity,s.pointerEvents,s.mixBlendMode])}});
            const c=document.elementFromPoint(300,400);return JSON.stringify({big:o.slice(0,14),top:c&&[c.tagName,c.id,String(c.className).slice(0,40)],bodyc:document.body.className,main:getComputedStyle(document.querySelector('main')).opacity})}"""))
            await pg.close()
        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s4_dbg6.py 2>&1 | tail -c 3000
