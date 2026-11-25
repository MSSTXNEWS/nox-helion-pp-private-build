#!/bin/bash
# s2_shot_music.sh: Playwright 1440x900, 3840x2160, 390x844; клики по кнопкам; JPEG q38 в base64
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
cat > /tmp/s4_shot.py <<'PYEOF'
import asyncio,base64,io,sys,json
from playwright.async_api import async_playwright
import os
PAGES=os.environ.get("S4P","training").split(",")
B="http://127.0.0.1:8091/web/"
try:
    from PIL import Image
except Exception: Image=None
def emit(name,raw,w):
    if Image:
        im=Image.open(io.BytesIO(raw)).convert('RGB')
        if im.width>w: im=im.resize((w,int(im.height*w/im.width)))
        b=io.BytesIO(); im.save(b,'JPEG',quality=38,optimize=True); raw=b.getvalue()
    s=base64.b64encode(raw).decode()
    print("B64_%s_BEGIN"%name)
    for i in range(0,len(s),900): print(s[i:i+900])
    print("B64_%s_END"%name)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        for music in PAGES:
            for vp,(w,h,ow) in {"d":(1440,900,1000),"k":(3840,2160,1100),"m":(390,844,390)}.items():
                ctx=await b.new_context(viewport={"width":w,"height":h}); pg=await ctx.new_page(); errs=[];bad=[]
                pg.on("pageerror",lambda e:errs.append(str(e)[:140])); pg.on("response",lambda r:bad.append(str(r.status)+" "+r.url[-70:]) if r.status>=400 else None)
                pg.on("filechooser",lambda fc:None); pg.on("dialog",lambda d:asyncio.ensure_future(d.dismiss()))
                await pg.goto(B+music+".html",wait_until="load",timeout=40000); await pg.wait_for_timeout(5000)
                ov=await pg.evaluate("()=>[document.documentElement.scrollWidth,innerWidth]")
                raw=await pg.screenshot(type="jpeg",quality=60); emit(music+"_"+vp,raw,ow)
                print("VP",vp,"overflow",ov,"errs",errs[:4],"bad",bad[:5])
                if vp in("d","m"):
                    n=await pg.evaluate("()=>{const q=[...document.querySelectorAll('.wrap button,.wrap summary,.wrap [data-c]')].filter(e=>e.offsetParent&&e.getBoundingClientRect().width>0);return q.length}")
                    small=await pg.evaluate("()=>[...document.querySelectorAll('.wrap button,.wrap input,.wrap select')].filter(e=>e.offsetParent&&(e.getBoundingClientRect().height<43)&&e.getBoundingClientRect().width>0).map(e=>(e.id||e.className||e.tagName).toString().slice(0,24)+':'+Math.round(e.getBoundingClientRect().height)).slice(0,12)")
                    print("VP",vp,"clickable",n,"small(<44)",small)
                    fails=0
                    for i in range(min(n,70)):
                        try:
                            ok=await pg.evaluate("(i)=>{const q=[...document.querySelectorAll('.wrap button,.wrap summary,.wrap [data-c]')].filter(e=>e.offsetParent&&e.getBoundingClientRect().width>0);const e=q[i];if(!e)return 0;if(e.tagName==='A'){e.removeAttribute('target');e.setAttribute('href','#')}e.scrollIntoView({block:'center'});return 1}",i)
                            if not ok: continue
                            await pg.evaluate("(i)=>{const q=[...document.querySelectorAll('.wrap button,.wrap summary,.wrap [data-c]')].filter(e=>e.offsetParent&&e.getBoundingClientRect().width>0);q[i].click()}",i)
                            await pg.wait_for_timeout(120)
                            if i==2 and vp=="d": 
                                raw=await pg.screenshot(type="jpeg",quality=60); emit(music+"_click",raw,700)
                            await pg.keyboard.press("Escape")
                        except Exception as e: fails+=1; print("CLICKFAIL",i,str(e)[:80])
                    print("VP",vp,"clicked",min(n,70),"fails",fails,"errs",errs[:4])
                await ctx.close()

        await b.close()
asyncio.run(main())
PYEOF
$PY /tmp/s4_shot.py 2>&1 | tail -c 700000
