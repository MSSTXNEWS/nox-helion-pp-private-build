#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
ffmpeg -y -loglevel error -f lavfi -i testsrc=size=640x360:rate=24:duration=12 -f lavfi -i sine=frequency=440:duration=12 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest /tmp/s2_t.mp4
cat > /tmp/s2_vid.py <<'PYEOF'
import asyncio,base64,io
from playwright.async_api import async_playwright
from PIL import Image
B="http://127.0.0.1:8091/web/"
def emit(name,raw,w):
    im=Image.open(io.BytesIO(raw)).convert('RGB')
    if im.width>w: im=im.resize((w,int(im.height*w/im.width)))
    b=io.BytesIO(); im.save(b,'JPEG',quality=34,optimize=True); s=base64.b64encode(b.getvalue()).decode()
    print("B64_%s_BEGIN"%name)
    for i in range(0,len(s),900): print(s[i:i+900])
    print("B64_%s_END"%name)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist","--autoplay-policy=no-user-gesture-required"])
        for vp,(w,h) in {"d":(1440,900),"m":(390,844)}.items():
            ctx=await b.new_context(viewport={"width":w,"height":h}); pg=await ctx.new_page(); errs=[]
            pg.on("pageerror",lambda e:errs.append(str(e)[:160])); pg.on("console",lambda m:errs.append("C:"+m.text[:140]) if m.type=="error" else None)
            await pg.goto(B+"cinema.html",wait_until="load"); await pg.wait_for_timeout(3500)
            print("VS defined",await pg.evaluate("()=>[!!window.NOX_vidstack,!!customElements.get('media-player'),!!customElements.get('media-video-layout')]"))
            await pg.set_input_files("#fV","/tmp/s2_t.mp4"); await pg.wait_for_timeout(4500)
            print(vp,"player",await pg.evaluate("()=>{const v=document.querySelector('#cnPl video');return [!!document.querySelector('#cnPl media-player'),!!v,v&&v.readyState,v&&Math.round(v.currentTime*10)/10,!!document.querySelector('#cnPl media-controls')]}"))
            emit("vs_"+vp,await pg.screenshot(type="jpeg",quality=60),900 if vp=="d" else 390)
            if vp=="d":
                await pg.click("[data-act=as]"); await pg.wait_for_timeout(300)
                await pg.click("[data-act=ru]"); await pg.wait_for_timeout(9000)
                print("LIVE status",await pg.evaluate("()=>document.querySelector('#cnLiveSt').textContent"))
                emit("vs_live",await pg.screenshot(type="jpeg",quality=60),900)
                await pg.click("[data-act=ru]"); await pg.wait_for_timeout(300)
                print("LIVE off",await pg.evaluate("()=>document.querySelector('#cnLiveSt').textContent"))
            print(vp,"errs",errs[:6])
            await ctx.close()
        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s2_vid.py 2>&1 | tail -c 300000
