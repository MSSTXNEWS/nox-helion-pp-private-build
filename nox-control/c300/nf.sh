#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/nox-dock-wow.js -o /workspace/nox/web/site/nox-dock-wow.js; curl -fsSL $R/nf.py -o /tmp/nf.py && python3 /tmp/nf.py
ls /workspace/nox/web/site/vendor/nox-x/fx2/; grep -c "nox-dock-wow" /workspace/nox/web/site/nox-nav.js
cat > /tmp/dt.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-unsafe-swiftshader"])
        for page in ("index.html","cinema.html","tools.html","chat.html","settings.html"):
            pg=await b.new_page(viewport={"width":1400,"height":860}); errs=[]
            pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)[:120]))
            await pg.goto("http://127.0.0.1:8091/web/"+page); await pg.wait_for_timeout(3500)
            r=await pg.evaluate("({dock:document.querySelectorAll('.nw-dock .nw-cat').length, pops:document.querySelectorAll('.nw-pop .nw-btn').length, top:document.querySelectorAll('.nw-top a').length, space:!!document.getElementById('space'), oldDock:getComputedStyle(document.querySelector('.nox-dock')||document.body).display})")
            await pg.hover(".nw-cat:nth-child(5) .nw-btn"); await pg.wait_for_timeout(500)
            op=await pg.evaluate("document.querySelector('.nw-cat:nth-child(5)').classList.contains('open')")
            print(page, r, "hover-open", op, "errs", errs[:2]); await pg.close()
        await b.close()
asyncio.run(main())
P
timeout 120 /workspace/nox/venv/bin/python /tmp/dt.py 2>&1 | tail -8
