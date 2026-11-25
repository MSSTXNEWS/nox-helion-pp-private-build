#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
ffmpeg -y -loglevel error -f lavfi -i "testsrc2=size=800x500:rate=1" -frames:v 1 /tmp/s2_t.jpg
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
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        ctx=await b.new_context(viewport={"width":1440,"height":900}); pg=await ctx.new_page(); errs=[]
        pg.on("pageerror",lambda e:errs.append(str(e)[:160])); pg.on("console",lambda m:errs.append("C:"+m.text[:140]) if m.type=="error" else None)
        await pg.goto(B+"news.html",wait_until="domcontentloaded"); await pg.wait_for_timeout(2500)
        await pg.click("#nwGl"); await pg.wait_for_timeout(6000)
        print("labels",await pg.evaluate("()=>document.querySelectorAll('#nwGc div').length"))
        emit("i_news",await pg.screenshot(type="jpeg",quality=60),900); print("NEWS errs",errs[-3:]); errs.clear()
        r=await pg.evaluate("async()=>{try{const x=await fetch('/svc/tts2/health');return x.status+' '+(await x.text()).slice(0,120)}catch(e){return String(e)}}"); print("TTS2",r)
        await pg.goto(B+"studio.html",wait_until="domcontentloaded"); await pg.wait_for_timeout(2500)
        await pg.set_input_files("#stDf","/tmp/s2_t.jpg")
        for i in range(30):
            await pg.wait_for_timeout(5000)
            t=await pg.inner_text("#d25s")
            if t.startswith("Готово") or t.startswith("Не получилось"): break
        print("DEPTH",t[:200])
        emit("i_depth",await pg.screenshot(type="jpeg",quality=60),900); print("STUDIO errs",errs[-3:]); errs.clear()
        await pg.goto(B+"editor.html",wait_until="domcontentloaded"); await pg.wait_for_timeout(2000); print("EDITOR url",pg.url)
        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s2_feat.py 2>&1 | tail -c 300000
