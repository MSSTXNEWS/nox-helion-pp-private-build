#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python
cat > /tmp/nw.py <<'P'
import asyncio,time
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1440,"height":900}); errs=[]
        pg.on("pageerror",lambda e:errs.append(str(e)[:120])); n=[0]
        pg.on("request",lambda r:n.__setitem__(0,n[0]+1))
        t=time.time(); await pg.goto("http://127.0.0.1:8091/web/news.html",wait_until="load"); t1=time.time()-t
        await pg.wait_for_selector(".nw-lead a, a.nw-lead",timeout=15000); t2=time.time()-t
        print("load",round(t1*1000),"lead",round(t2*1000),"requests",n[0])
        print("first buttons",await pg.evaluate("""()=>[...document.querySelectorAll('button,sl-button,[role=button]')].filter(e=>e.offsetParent).slice(0,4).map(e=>e.tagName+'#'+e.id+'.'+(e.className||'').toString().slice(0,30)+':'+(e.textContent||e.getAttribute('aria-label')||'').trim().slice(0,20)+':'+Math.round(e.getBoundingClientRect().top))"""))
        print("errs",errs); await b.close()
asyncio.run(main())
P
$PY /tmp/nw.py 2>&1 | tail -8
