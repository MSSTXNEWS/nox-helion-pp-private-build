echo S4RUN:s6_p9
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_p9.py <<'PYEOF'
import asyncio,json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        for pn,sel in [("map","#mpMap"),("benchmark","#bmCh"),("nexus","#nxG")]:
            pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page(); errs=[]
            pg.on("pageerror",lambda e:errs.append(str(e)[:160])); pg.on("console",lambda m:errs.append("C:"+m.text[:120]) if m.type=="error" else None)
            await pg.goto("http://127.0.0.1:8091/web/%s.html"%pn,wait_until="load",timeout=60000); await pg.wait_for_timeout(9000)
            print("DBG",pn,errs[:5],await pg.evaluate("(s)=>{const e=document.querySelector(s);if(!e)return 'none';const r=e.getBoundingClientRect();const c=getComputedStyle(e);return [Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height),c.display,c.visibility,c.opacity,e.children.length,!!window.echarts,!!window.L,!!window.cytoscape,document.getElementById('s6root').innerHTML.length]}",sel))
asyncio.run(main())
PYEOF
$PY /tmp/s6_p9.py 2>&1 | tail -12
