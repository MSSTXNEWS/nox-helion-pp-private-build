echo S4RUN:s6_n2
cd /workspace/nox/web/site
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; $PY -c 'import playwright' 2>/dev/null || PY=python3
cat > /tmp/s6_shot.py <<'S6EOF_PY'
import asyncio,base64,io,os,json
from playwright.async_api import async_playwright
from PIL import Image
PAGES=os.environ.get("S6P","photo").split(","); CLK=os.environ.get("S6CLICK","1")=="1"
B="http://127.0.0.1:8091/web/"
def emit(name,raw,w):
    im=Image.open(io.BytesIO(raw)).convert('RGB')
    if im.width>w: im=im.resize((w,int(im.height*w/im.width)))
    b=io.BytesIO(); im.save(b,'JPEG',quality=35,optimize=True); s=base64.b64encode(b.getvalue()).decode()
    print("B64_%s_BEGIN"%name)
    for i in range(0,len(s),900): print(s[i:i+900])
    print("B64_%s_END"%name)
JS_STAT="""()=>{const v=e=>e.offsetParent&&e.getBoundingClientRect().width>0;
const nat=[...document.querySelectorAll('main.page button,main.page select,main.page textarea,main.page input:not([type=file])')].filter(v).filter(e=>!e.closest('[class*=FIE_],.plyr,.swiper,sl-dialog,.cm-editor,canvas')).map(e=>(e.id||e.className||e.tagName).toString().slice(0,22));
const sl=[...document.querySelectorAll('sl-button.s6sl,sl-select,sl-input,sl-textarea,sl-checkbox,sl-range')].filter(v).length;
const small=[...document.querySelectorAll('main.page sl-button,main.page sl-select,main.page sl-input')].filter(v).filter(e=>e.getBoundingClientRect().height<43).length;
const fs=[...document.querySelectorAll('main.page *')].filter(e=>e.children.length==0&&e.textContent.trim()&&v(e)&&parseFloat(getComputedStyle(e).fontSize)<12).length;
return {native:nat.length,nativeList:nat.slice(0,8),sl:sl,small:small,fs12:fs,ow:[document.documentElement.scrollWidth,innerWidth]}}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        for pg_ in PAGES:
            for vp,(w,h,ow) in {"d":(1440,900,1000),"m":(390,844,390)}.items():
                ctx=await b.new_context(viewport={"width":w,"height":h}); pg=await ctx.new_page(); errs=[]; reqs=[]
                pg.on("pageerror",lambda e:errs.append(str(e)[:120])); pg.on("request",lambda r:reqs.append(r.url[-40:]) if r.method=="POST" or "/api/" in r.url else None)
                pg.on("filechooser",lambda fc:None); pg.on("dialog",lambda d:asyncio.ensure_future(d.dismiss()))
                try: await pg.goto(B+pg_+".html",wait_until="load",timeout=40000)
                except Exception as e: print("GOTO",pg_,str(e)[:80])
                await pg.wait_for_timeout(5500)
                raw=await pg.screenshot(type="jpeg",quality=60); emit(pg_+"_"+vp,raw,ow)
                print("STAT",pg_,vp,json.dumps(await pg.evaluate(JS_STAT),ensure_ascii=False),"errs",errs[:3])
                if vp=="d" and CLK:
                    n=await pg.evaluate("()=>document.querySelectorAll('main.page sl-button.s6sl').length"); dead=0; e0=len(errs)
                    for i in range(min(n,45)):
                        try:
                            sig0=await pg.evaluate("()=>document.body.innerHTML.length+'|'+document.querySelectorAll('sl-dialog[open]').length"); r0=len(reqs)
                            await pg.evaluate("(i)=>{const e=document.querySelectorAll('main.page sl-button.s6sl')[i];if(e&&!e.disabled){e.scrollIntoView({block:'center'});e.click()}}",i)
                            await pg.wait_for_timeout(150)
                            sig1=await pg.evaluate("()=>document.body.innerHTML.length+'|'+document.querySelectorAll('sl-dialog[open]').length")
                            if sig0==sig1 and len(reqs)==r0: dead+=1
                            await pg.keyboard.press("Escape")
                        except Exception as e: pass
                    print("CLICK",pg_,"sl-buttons",n,"no-visible-effect",dead,"newerrs",errs[e0:e0+3])
                await ctx.close()
        await b.close()
asyncio.run(main())
S6EOF_PY
S6CLICK=1 S6P=music,studio,creative,board $PY /tmp/s6_shot.py 2>&1 | tail -n 2000
