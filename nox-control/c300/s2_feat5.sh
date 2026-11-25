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
        await pg.goto(B+"board.html",wait_until="domcontentloaded"); await pg.wait_for_timeout(6000)
        emit("j_board0",await pg.screenshot(type="jpeg",quality=60),900); print("errs0",errs[-3:]); errs.clear()
        await pg.click('[data-tp="kanban"]'); await pg.wait_for_timeout(1500)
        print("kanban elements",await pg.evaluate("()=>JSON.parse(localStorage.getItem('nox.s2.board')||'{}').elements?.length"))
        emit("j_kanban",await pg.screenshot(type="jpeg",quality=60),900)
        await pg.click('[data-tp="mind"]'); await pg.wait_for_timeout(1000)
        await pg.fill("#bdIn","запуск продукта: маркетинг, разработка, поддержка, финансы, юридические вопросы"); await pg.click('[data-a="ai"]'); await pg.wait_for_timeout(9000)
        emit("j_ai_mid",await pg.screenshot(type="jpeg",quality=60),900)
        for i in range(20):
            await pg.wait_for_timeout(3000)
            t=await pg.inner_text("#bdSt")
            if t.startswith("Готово") or t.startswith("NOX занят"): break
        print("AI status",t); emit("j_ai_end",await pg.screenshot(type="jpeg",quality=60),900); print("errs",errs[-3:]); errs.clear()
        c2=await b.new_context(viewport={"width":390,"height":844}); p2=await c2.new_page()
        await p2.goto(B+"board.html",wait_until="domcontentloaded"); await p2.wait_for_timeout(5000)
        emit("j_board_m",await p2.screenshot(type="jpeg",quality=60),390)
        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s2_feat.py 2>&1 | tail -c 300000
