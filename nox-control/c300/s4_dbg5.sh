echo S4RUN:s4_dbg5
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
cat > /tmp/s4_dbg5.py <<'PYEOF'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        pg=await b.new_page(viewport={"width":1440,"height":900}); msgs=[]
        pg.on("console",lambda m:msgs.append(m.text[:200])); pg.on("pageerror",lambda e:msgs.append("ERR "+str(e)[:200]))
        await pg.goto("http://127.0.0.1:8091/web/selffeel.html",wait_until="load"); await pg.wait_for_timeout(6000)
        print(await pg.evaluate("""()=>{const P=window.NOX_paper_design_shaders;const d=document.querySelector('.s4drop');const c=d&&d.querySelector('canvas');
        return JSON.stringify({keys:Object.keys(P||{}).slice(0,40),meta:P&&P.metaballsMeta,sizing:P&&P.defaultObjectSizing,drop:d&&d.getBoundingClientRect(),canvas:c&&[c.width,c.height,c.getBoundingClientRect().width],hasMount:!!window.__s4drop,html:d&&d.innerHTML.slice(0,200)})}"""))
        print(msgs[:8]); await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s4_dbg5.py 2>&1 | tail -c 2500
