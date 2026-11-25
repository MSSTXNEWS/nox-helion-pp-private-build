echo S4RUN:s6_p3
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_p3.py <<'PYEOF'
import asyncio,json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
        await pg.goto("http://127.0.0.1:8091/web/settings.html",wait_until="domcontentloaded",timeout=60000); await pg.wait_for_timeout(5000)
        print("DOTS",await pg.evaluate("()=>{const h=[...document.querySelectorAll('.nxwd')].map(e=>e.outerHTML.slice(-900));return h}"))
        res=await pg.evaluate('''async()=>{const out=[];const dots=[...document.querySelectorAll('.nxwd [data-pal],.nxwd [data-c],.nxwd-p button,.nxwd button[title]')];const all=[...document.querySelectorAll('.nxwd button')].filter(b=>!b.dataset.w);for(const d of all){d.click();await new Promise(r=>setTimeout(r,600));const cs=n=>getComputedStyle(n);out.push([d.title||d.getAttribute('aria-label')||d.className,localStorage.getItem('nox.world.pal'),cs(document.body).getPropertyValue('--cy').trim(),cs(document.documentElement).getPropertyValue('--cy').trim(),cs(document.documentElement).getPropertyValue('--am').trim()])}return out}''')
        for r in res: print("PALC",json.dumps(r,ensure_ascii=False))
asyncio.run(main())
PYEOF
$PY /tmp/s6_p3.py 2>&1 | tail -20
grep -c "<img" /workspace/nox/web/site/nox-s2-music.js; grep -o "<img[^>]\{0,80\}" /workspace/nox/web/site/nox-s2-music.js | head -4
