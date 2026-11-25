#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
ffmpeg -y -loglevel error -f lavfi -i testsrc2=size=640x360:rate=25 -f lavfi -i sine=frequency=440 -t 8 -pix_fmt yuv420p -c:v libx264 -c:a aac /tmp/s2_test.mp4
cat > /tmp/s2_feat.py <<'PYEOF'
import asyncio,base64,io
from playwright.async_api import async_playwright
from PIL import Image
B="http://127.0.0.1:8091/web/"
def emit(name,raw,w):
    im=Image.open(io.BytesIO(raw)).convert('RGB')
    if im.width>w: im=im.resize((w,int(im.height*w/im.width)))
    b=io.BytesIO(); im.save(b,'JPEG',quality=32,optimize=True); s=base64.b64encode(b.getvalue()).decode()
    print("B64_%s_BEGIN"%name)
    for i in range(0,len(s),900): print(s[i:i+900])
    print("B64_%s_END"%name)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist","--autoplay-policy=no-user-gesture-required"])
        ctx=await b.new_context(viewport={"width":1440,"height":900}); pg=await ctx.new_page(); errs=[]
        pg.on("pageerror",lambda e:errs.append(str(e)[:160])); pg.on("console",lambda m:errs.append("C:"+m.text[:140]) if m.type=="error" else None)
        await pg.goto(B+"news.html",wait_until="load"); await pg.wait_for_timeout(2500)
        await pg.click("#nwGl"); await pg.wait_for_timeout(6000)
        emit("g_news",await pg.screenshot(type="jpeg",quality=60),900); print("NEWS errs",errs[-3:]); errs.clear()
        await pg.goto(B+"cinema.html",wait_until="load"); await pg.wait_for_timeout(2500)
        await pg.set_input_files("#fV","/tmp/s2_test.mp4"); await pg.wait_for_timeout(2500)
        await pg.click("#cnHallB"); await pg.wait_for_timeout(3500)
        print("HALL",await pg.evaluate("()=>[!!document.querySelector('.cn-3d'),document.querySelector('#cnPl').classList.contains('hall')]"))
        emit("g_hall",await pg.screenshot(type="jpeg",quality=60),900); print("CINEMA errs",errs[-3:]); errs.clear()
        await pg.goto(B+"creative.html",wait_until="load"); await pg.wait_for_timeout(3000)
        for t in ["rect","ell","txt"]:
            await pg.click('[data-t="%s"]'%t); await pg.wait_for_timeout(300)
        await pg.fill("#gP","тестовый постер"); await pg.click('[data-g="1"]'); await pg.click('[data-a="gen"]'); await pg.wait_for_timeout(2500)
        print("CREATIVE layers",await pg.evaluate("()=>document.querySelectorAll('#crL .cr-ly').length"),"status",await pg.inner_text("#gSt"))
        emit("g_creative",await pg.screenshot(type="jpeg",quality=60),900); print("CREATIVE errs",errs[-3:]); errs.clear()
        await pg.goto(B+"tv.html",wait_until="load"); await pg.wait_for_timeout(2500)
        await pg.keyboard.press("ArrowRight"); await pg.keyboard.press("ArrowRight"); await pg.wait_for_timeout(500)
        print("TV focus",await pg.evaluate("()=>document.activeElement.textContent.slice(0,20)"))
        emit("g_tv",await pg.screenshot(type="jpeg",quality=60),900); print("TV errs",errs[-3:]); errs.clear()
        c2=await b.new_context(viewport={"width":390,"height":844}); p2=await c2.new_page()
        await p2.goto(B+"creative.html",wait_until="load"); await p2.wait_for_timeout(3000)
        emit("g_cr_m",await p2.screenshot(type="jpeg",quality=60),390)
        await p2.goto(B+"tv.html",wait_until="load"); await p2.wait_for_timeout(2000)
        emit("g_tv_m",await p2.screenshot(type="jpeg",quality=60),390)
        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s2_feat.py 2>&1 | tail -c 330000
