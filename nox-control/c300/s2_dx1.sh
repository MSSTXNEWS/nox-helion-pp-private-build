#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python
cat > /tmp/dx.py <<'P'
import asyncio,base64,io
from playwright.async_api import async_playwright
from PIL import Image
def emit(n,raw,w=900):
    im=Image.open(io.BytesIO(raw)).convert('RGB'); im=im.resize((w,int(im.height*w/im.width))); b=io.BytesIO(); im.save(b,'JPEG',quality=34); s=base64.b64encode(b.getvalue()).decode()
    print("B64_%s_BEGIN"%n); [print(s[i:i+900]) for i in range(0,len(s),900)]; print("B64_%s_END"%n)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1440,"height":900}); errs=[]
        pg.on("pageerror",lambda e:errs.append(str(e)[:150])); bad=[]
        pg.on("response",lambda r:bad.append(str(r.status)+r.url[-60:]) if r.status>=400 else None)
        await pg.goto("http://127.0.0.1:8091/web/board.html"); await pg.wait_for_timeout(4500)
        emit("dx_board",await pg.screenshot(type="jpeg",quality=60))
        await pg.click("#bdMode"); await pg.wait_for_timeout(12000)
        fr=[f for f in pg.frames if 'drawio' in f.url]
        print("drawio frame",bool(fr), await fr[0].evaluate("()=>!!document.querySelector('.geEditor,.geDiagramContainer')") if fr else '')
        emit("dx_draw",await pg.screenshot(type="jpeg",quality=60))
        print("board errs",errs[:3],"bad",bad[:4]); errs.clear(); bad.clear()
        await pg.goto("http://127.0.0.1:8091/web/photo.html"); await pg.wait_for_timeout(4000)
        print("switch",await pg.evaluate("()=>{const s=document.querySelector('#cSee');return [s&&s.tagName,s&&Math.round(s.getBoundingClientRect().height)]}"))
        await pg.click("#cSee"); await pg.wait_for_timeout(300)
        print("checked",await pg.evaluate("()=>document.querySelector('#cSee').checked"))
        emit("dx_photo",await pg.screenshot(type="jpeg",quality=60)); print("photo errs",errs[:3])
        await b.close()
asyncio.run(main())
P
$PY /tmp/dx.py 2>&1 | tail -c 200000
