echo S4RUN:s6_r10
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_r10.py <<'PYEOF'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"]); 
        for page,sel in [("scene","#worlds"),("effects","#lvls"),("effects","#tg"),("effects","#det")]:
            pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
            await pg.goto("http://127.0.0.1:8091/web/%s.html"%page,wait_until="load"); await pg.wait_for_timeout(4000)
            print("#####",page,sel); print((await pg.evaluate("(s)=>{const e=document.querySelector(s);return e?e.outerHTML.slice(0,1300):'none'}",sel)))
asyncio.run(main())
PYEOF
$PY /tmp/s6_r10.py 2>&1 | tail -20
head -c 1500 /workspace/nox/web/site/nox-p-scene.js
