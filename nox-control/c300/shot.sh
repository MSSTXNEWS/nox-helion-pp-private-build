#!/bin/bash
curl -s -m5 127.0.0.1:8091/img/health | head -c 200; echo
cat > /tmp/shot.py <<'P'
import asyncio, base64, time
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-unsafe-swiftshader"]); pg=await b.new_page(viewport={"width":1500,"height":930})
        await pg.goto("http://127.0.0.1:8091/web/photo.html"); await pg.wait_for_timeout(5000); await pg.keyboard.press("Escape")
        await pg.fill("#cIn","Нарисуй уютный домик в горах ночью, северное сияние, неоновые огни в окнах"); await pg.click("#cGo", force=True)
        t=time.time()
        for i in range(80):
            await pg.wait_for_timeout(2500)
            txt=await pg.inner_text("#cLog")
            if "Готово" in txt or "занята" in txt or "не ответил" in txt: break
        print("dialog:", (await pg.inner_text("#cLog")).replace("\n"," | ")[:600], "| %.0fs"%(time.time()-t)); print("gen status:", await pg.inner_text("#gSt"))
        await pg.wait_for_timeout(2500)
        img=await pg.screenshot(type="jpeg", quality=62)
        print("SHOT_B64_BEGIN"); print(base64.b64encode(img).decode()); print("SHOT_B64_END"); await b.close()
asyncio.run(main())
P
timeout 270 /workspace/nox/venv/bin/python /tmp/shot.py 2>&1 | tail -6
