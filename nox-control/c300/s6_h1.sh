echo S4RUN:s6_h1
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_h1.py <<'PYEOF'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        for page in ["music","studio"]:
            ctx=await b.new_context(viewport={"width":1440,"height":900}); pg=await ctx.new_page(); errs=[]
            pg.on("pageerror",lambda e:errs.append((str(e)[:100],(e.stack or '')[:300]))); pg.on("dialog",lambda d:asyncio.ensure_future(d.dismiss())); pg.on("filechooser",lambda f:None)
            await pg.goto("http://127.0.0.1:8091/web/%s.html"%page,wait_until="load"); await pg.wait_for_timeout(5000)
            n=await pg.evaluate("()=>document.querySelectorAll('main.page sl-button.s6sl').length")
            for i in range(n):
                info=await pg.evaluate("(i)=>{const e=document.querySelectorAll('main.page sl-button.s6sl')[i];return [e.textContent.trim().slice(0,30),e.dataset.s6for,e.hasAttribute('disabled')]}",i)
                s0=await pg.evaluate("()=>document.body.innerHTML.length"); e0=len(errs)
                await pg.evaluate("(i)=>document.querySelectorAll('main.page sl-button.s6sl')[i].click()",i); await pg.wait_for_timeout(200)
                s1=await pg.evaluate("()=>document.body.innerHTML.length")
                print(page,i,info,"changed" if s0!=s1 else "NOEFFECT",errs[e0:])
                await pg.keyboard.press("Escape")
asyncio.run(main())
PYEOF
$PY /tmp/s6_h1.py 2>&1 | tail -60
grep -n "\.p\b" /workspace/nox/web/site/nox-s2-studio.js | head -5 | cut -c1-200
