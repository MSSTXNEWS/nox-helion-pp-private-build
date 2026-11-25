#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
ffmpeg -y -loglevel error -f lavfi -i 'sine=frequency=330:duration=8' -f lavfi -i 'sine=frequency=660:duration=8' -filter_complex amix /tmp/s2_test.wav
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
        for name,url,act in [("h_cinema","cinema.html",None),("h_studio","studio.html",None),("h_photo","photo.html",None),("h_creative","creative.html",None)]:
            await pg.goto(B+url,wait_until="load"); await pg.wait_for_timeout(4000)
            emit(name,await pg.screenshot(type="jpeg",quality=60),900); print(name,"errs",errs[-3:]); errs.clear()
        await pg.goto(B+"news.html",wait_until="load"); await pg.wait_for_timeout(3000)
        await pg.evaluate("()=>{const p=document.querySelector('#page');p.scrollTop=700}"); await pg.wait_for_timeout(800)
        emit("h_news",await pg.screenshot(type="jpeg",quality=60),900); print("news errs",errs[-3:]); errs.clear()
        await pg.goto(B+"music.html",wait_until="load"); await pg.wait_for_timeout(2500)
        await pg.set_input_files("#muF","/tmp/s2_test.wav"); await pg.wait_for_timeout(500)
        await pg.click(".mu-tr"); await pg.wait_for_timeout(3500)
        print("WAVE",await pg.evaluate("()=>[!!document.querySelector('#bWv canvas'),!!document.querySelector('#bWv div'),document.querySelector('#bWv').style.display]"))
        emit("h_music",await pg.screenshot(type="jpeg",quality=60),900); print("music errs",errs[-3:])
        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s2_feat.py 2>&1 | tail -c 330000
