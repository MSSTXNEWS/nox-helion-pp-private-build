echo S4RUN:s6_p2
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_p2.py <<'PYEOF'
import asyncio,json,time
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        for pn in ["music","photo","projects","widgets"]:
            pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
            await pg.goto("http://127.0.0.1:8091/web/%s.html"%pn,wait_until="domcontentloaded",timeout=60000); await pg.wait_for_timeout(6000)
            print("SELECT",pn,await pg.evaluate("()=>[...document.querySelectorAll('select')].map(e=>[e.id,e.offsetParent!=null,getComputedStyle(e).display]).filter(x=>x[1])"))
        pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page(); bad=[]
        pg.on("response",lambda r:bad.append(str(r.status)+" "+r.url[-50:]) if r.status>=400 else None)
        await pg.goto("http://127.0.0.1:8091/web/about.html",wait_until="load",timeout=60000); await pg.wait_for_timeout(9000); print("ABOUT bad",bad)
        for i in range(3):
            pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page(); t0=time.time()
            await pg.goto("http://127.0.0.1:8091/web/music.html",wait_until="load",timeout=60000); t1=time.time()-t0
            print("MUSIC load",round(t1,2),await pg.evaluate("()=>{const e=performance.getEntriesByType('resource').sort((a,b)=>b.duration-a.duration).slice(0,4).map(r=>r.name.slice(-40)+':'+Math.round(r.duration));const n=performance.getEntriesByType('resource').length;return [n,e]}"))
        pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
        await pg.goto("http://127.0.0.1:8091/web/settings.html",wait_until="domcontentloaded",timeout=60000); await pg.wait_for_timeout(5000)
        print("PAL html",await pg.evaluate("()=>{const h=[...document.querySelectorAll('*')].find(e=>e.children.length==0&&/Палитра сцены/i.test(e.textContent));if(!h)return 'nohdr';let n=h.parentElement;return (n.outerHTML||'').slice(0,900)}"))
        keys0=await pg.evaluate("()=>JSON.stringify(Object.assign({},localStorage))")
        res=await pg.evaluate('''async()=>{const h=[...document.querySelectorAll('*')].find(e=>e.children.length==0&&/Палитра сцены/i.test(e.textContent));if(!h)return 'nohdr';const box=h.parentElement;const dots=[...box.querySelectorAll('button,[role=button],[data-pal],[data-p],[data-c],sl-button,div[title]')].filter(e=>e.getBoundingClientRect().width>10&&e.getBoundingClientRect().width<70);const out=[];for(const d of dots.slice(0,8)){d.click();await new Promise(r=>setTimeout(r,500));out.push([d.getAttribute('title')||d.getAttribute('data-pal')||d.getAttribute('data-p')||d.className,getComputedStyle(document.documentElement).getPropertyValue('--cy').trim()+'|'+getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),(localStorage.getItem('nox.scene.palette')||localStorage.getItem('nox-pal')||'').slice(0,60)])}return out}''')
        print("PAL clicks",json.dumps(res,ensure_ascii=False))
        print("LS keys",await pg.evaluate("()=>Object.keys(localStorage).filter(k=>/pal|scene|world|theme/i.test(k))"))
asyncio.run(main())
PYEOF
$PY /tmp/s6_p2.py 2>&1 | tail -30
export S6CLICK=0
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
S6CLICK=0 S6P=map,book-reader,notifications,benchmark,nexus $PY /tmp/s6_shot.py 2>&1 | tail -n 700
