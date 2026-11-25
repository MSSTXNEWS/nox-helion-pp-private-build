echo S4RUN:s6_v2c
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_q3.py <<'PYEOF'
import asyncio,json
from playwright.async_api import async_playwright
PAGES="intents models scene effects widgets about integrations glance install settings".split()
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
        await pg.goto("http://127.0.0.1:8091/web/studio.html",wait_until="domcontentloaded",timeout=60000); await pg.wait_for_timeout(4500)
        print("STUDIO",await pg.evaluate("()=>[...document.querySelectorAll('select,sl-select')].map(e=>e.tagName+'#'+e.id+' disp='+getComputedStyle(e).display+' cls='+e.className+' vis='+(e.offsetParent!=null)+' par='+e.parentElement.className)"))
        for w,h in [(1440,900),(3840,2160)]:
            for pn in PAGES:
                ctx=await b.new_context(viewport={"width":w,"height":h}); pg=await ctx.new_page(); errs=[]
                pg.on("pageerror",lambda e:errs.append(str(e)[:80]))
                try: await pg.goto("http://127.0.0.1:8091/web/%s.html"%pn,wait_until="domcontentloaded",timeout=60000)
                except Exception as e: print("GOTO",pn,w); 
                await pg.wait_for_timeout(2500)
                r=await pg.evaluate("""()=>{const v=e=>e.offsetParent&&e.getBoundingClientRect().width>0;
const wide=[...document.querySelectorAll('main.page *')].filter(e=>v(e)&&e.getBoundingClientRect().right>innerWidth+2&&!e.closest('canvas,.swiper,.scroll-x,[class*=scroll],.fc,.drawflow,table')).map(e=>(e.id||e.className||e.tagName).toString().slice(0,18)).slice(0,3);
const small=[...document.querySelectorAll('main.page sl-button,main.page sl-input,main.page sl-select,main.page sl-checkbox')].filter(v).filter(e=>e.getBoundingClientRect().height<43).map(e=>(e.tagName+':'+(e.textContent||'').trim().slice(0,14)+':'+Math.round(e.getBoundingClientRect().height))).slice(0,4);
const fs=[...document.querySelectorAll('main.page *')].filter(e=>e.children.length==0&&e.textContent.trim()&&v(e)&&parseFloat(getComputedStyle(e).fontSize)<12).map(e=>e.tagName+'.'+String(e.className).slice(0,14)+'='+getComputedStyle(e).fontSize).slice(0,4);
return {ow:document.documentElement.scrollWidth-innerWidth,wide,small,fs12:fs,ask:!!document.getElementById('s6Ask')}}""")
                bad = r['ow']>2 or r['small'] or r['fs12'] or errs
                print("DIAG",w,pn,json.dumps(r,ensure_ascii=False) if bad else "ok",errs[:2])
                await ctx.close()
asyncio.run(main())
PYEOF
$PY /tmp/s6_q3.py 2>&1 | tail -80
