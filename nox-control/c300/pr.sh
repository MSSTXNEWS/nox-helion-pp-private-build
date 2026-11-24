#!/bin/bash
curl -s -m5 127.0.0.1:8091/img/health | head -c 900; echo
cat > /tmp/pp.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(); await pg.goto("http://127.0.0.1:8091/web/vendor/nox-x/minipaint/index.html"); await pg.wait_for_timeout(4000)
        print(await pg.evaluate("(()=>{const L=window.Layers;const m=[];for(const k in L)m.push(k);let pr=Object.getPrototypeOf(L);while(pr&&pr!==Object.prototype){m.push(...Object.getOwnPropertyNames(pr));pr=Object.getPrototypeOf(pr)};return {L:m.filter(x=>/canvas|dimen|width|size|export|render|insert|config/i.test(x)).slice(0,40), g:Object.keys(window).filter(k=>/^(config|State|FileOpen|AppConfig|Tools|Base|Helper|Dialog|GUI)/i.test(k))}})()"))
        print(await pg.evaluate("(()=>{const L=window.Layers; for (const k of ['config','app_config','Base_gui']) if (L[k]) return k+':'+JSON.stringify(Object.keys(L[k]).slice(0,20)); return 'no cfg on Layers'})()"))
        await b.close()
asyncio.run(main())
P
timeout 90 /workspace/nox/venv/bin/python /tmp/pp.py 2>&1 | tail -4
