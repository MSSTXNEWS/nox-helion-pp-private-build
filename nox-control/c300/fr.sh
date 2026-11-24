#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; S=/workspace/nox/web/site; D=$S/vendor/nox-x/filerobot; mkdir -p $D
[ -s $D/filerobot-image-editor.min.js ] || curl -fsSL -o $D/filerobot-image-editor.min.js https://scaleflex.cloudimg.io/v7/plugins/filerobot-image-editor/latest/filerobot-image-editor.min.js || curl -fsSL -o $D/filerobot-image-editor.min.js https://cdn.jsdelivr.net/npm/filerobot-image-editor@4/dist/filerobot-image-editor.min.js
ls -la $D
for f in photo.html nox-photo.js; do curl -fsSL $R/$f -o $S/$f; done
cat > /tmp/shot3.py <<'P'
import asyncio, base64, textwrap
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-unsafe-swiftshader"]); errs=[]
        for name,vp,q in (("desk",{"width":1440,"height":900},38),("mob",{"width":390,"height":844},40)):
            pg=await b.new_page(viewport=vp); pg.on("pageerror", lambda e: errs.append(str(e)[:150]))
            await pg.goto("http://127.0.0.1:8091/web/photo.html"); await pg.wait_for_timeout(7000); await pg.keyboard.press("Escape"); await pg.wait_for_timeout(700)
            img=await pg.screenshot(type="jpeg", quality=q)
            print("B64_"+name+"_BEGIN"); print("\n".join(textwrap.wrap(base64.b64encode(img).decode(), 900))); print("B64_"+name+"_END"); await pg.close()
        print("ERRS", errs[:4]); await b.close()
asyncio.run(main())
P
timeout 150 /workspace/nox/venv/bin/python /tmp/shot3.py 2>&1 | grep -v "^\s*$"
