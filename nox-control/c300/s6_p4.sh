echo S4RUN:s6_p4
cd /workspace/nox/web/site
grep -n "nox.world.pal" *.js | cut -c1-260 | head -8
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_p4.py <<'PYEOF'
import asyncio,json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
        await pg.goto("http://127.0.0.1:8091/web/settings.html",wait_until="domcontentloaded",timeout=60000); await pg.wait_for_timeout(5000)
        for name in ["Циан","Янтарь","Мята","Фиолет","Малина","Лазурь"]:
            loc=pg.locator('.nxwd button[aria-label="%s"]'%name)
            try:
                await loc.scroll_into_view_if_needed(timeout=3000); await loc.click(timeout=3000,force=True)
            except Exception as e: print("CLICKERR",name,str(e)[:80])
            await pg.wait_for_timeout(700)
            print("PAL",name,json.dumps(await pg.evaluate("()=>[localStorage.getItem('nox.world.pal'),getComputedStyle(document.documentElement).getPropertyValue('--cy').trim(),getComputedStyle(document.documentElement).getPropertyValue('--am').trim(),[...document.querySelectorAll('.nxwd button[role=radio][aria-checked=true]')].map(e=>e.getAttribute('aria-label')||e.dataset.w)]")))
asyncio.run(main())
PYEOF
$PY /tmp/s6_p4.py 2>&1 | tail -10
