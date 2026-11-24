#!/bin/bash
cat > /tmp/shot2.py <<'P'
import asyncio, base64, textwrap
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-unsafe-swiftshader"])
        for name,vp in (("desk",{"width":1500,"height":930}),("mob",{"width":390,"height":844})):
            pg=await b.new_page(viewport=vp, device_scale_factor=1); await pg.goto("http://127.0.0.1:8091/web/photo.html"); await pg.wait_for_timeout(6000); await pg.keyboard.press("Escape"); await pg.wait_for_timeout(800)
            img=await pg.screenshot(type="jpeg", quality=60, full_page=(name=="mob"))
            print("B64_"+name+"_BEGIN"); print("\n".join(textwrap.wrap(base64.b64encode(img).decode(), 4000))); print("B64_"+name+"_END"); await pg.close()
        await b.close()
asyncio.run(main())
P
for p in 8091 8104; do echo -n "$p=$(curl -s -m4 -o /dev/null -w %{http_code} 127.0.0.1:$p/health) "; done; echo; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
timeout 120 /workspace/nox/venv/bin/python /tmp/shot2.py 2>&1 | grep -v "^\s*$"
