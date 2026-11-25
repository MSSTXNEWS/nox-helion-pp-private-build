#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
which ffmpeg >/dev/null && ffmpeg -y -loglevel error -f lavfi -i testsrc2=size=640x360:rate=25 -f lavfi -i sine=frequency=440 -t 6 -pix_fmt yuv420p -c:v libx264 -c:a aac /tmp/s2_test.mp4 && ls -la /tmp/s2_test.mp4
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
        pg.on("pageerror",lambda e:errs.append(str(e)[:160])); pg.on("console",lambda m:errs.append("C:"+m.text[:120]) if m.type=="error" else None)
        # news + globe
        await pg.goto(B+"news.html",wait_until="load"); await pg.wait_for_timeout(2500)
        await pg.click("#nwGl"); await pg.wait_for_timeout(5000)
        emit("f_news",await pg.screenshot(type="jpeg",quality=60),900); print("NEWS errs",errs[-3:]); errs.clear()
        await pg.evaluate("()=>{const c=document.querySelector('#nwGc canvas');return !!c}")
        # music + viz
        await pg.goto(B+"music.html",wait_until="load"); await pg.wait_for_timeout(2500)
        await pg.click("#muViz"); await pg.wait_for_timeout(4000)
        emit("f_music",await pg.screenshot(type="jpeg",quality=60),900); print("MUSIC errs",errs[-3:], "viz canvas", await pg.evaluate("()=>!!document.querySelector('.mu-viz')")); errs.clear()
        # cinema + ambilight + local file
        await pg.goto(B+"cinema.html",wait_until="load"); await pg.wait_for_timeout(2500)
        try:
            await pg.set_input_files("#fV","/tmp/s2_test.mp4"); await pg.wait_for_timeout(3500)
            st=await pg.evaluate("()=>{const v=document.querySelector('#cnPl video');return v?[v.readyState,v.currentTime,v.paused,v.videoWidth,!!document.querySelector('#cnPl.amb')]:null}")
            print("PLAY state(ready,time,paused,w,amb)",st)
            emit("f_cinema",await pg.screenshot(type="jpeg",quality=60),900)
        except Exception as e: print("CINEMA ERR",str(e)[:200])
        print("CINEMA errs",errs[-3:]); errs.clear()
        # mobile cinema menu
        c2=await b.new_context(viewport={"width":390,"height":844}); p2=await c2.new_page()
        await p2.goto(B+"cinema.html",wait_until="load"); await p2.wait_for_timeout(2500)
        await p2.click(".cn-dots"); await p2.wait_for_timeout(400)
        emit("f_cmob",await p2.screenshot(type="jpeg",quality=60),390)
        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s2_feat.py 2>&1 | tail -c 300000
