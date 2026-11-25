echo S4RUN:s6_o1
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_o1.py <<'PYEOF'
import asyncio,json
from playwright.async_api import async_playwright
JS="""()=>{const cs=getComputedStyle(document.documentElement);const hh=parseFloat(cs.getPropertyValue('--ds-head-h'))||72,dh=parseFloat(cs.getPropertyValue('--ds-dock-h'))||111;
const out=[];document.querySelectorAll('body *').forEach(e=>{const s=getComputedStyle(e);if(s.position!=='fixed'&&s.position!=='sticky')return;if(s.visibility==='hidden'||s.display==='none'||parseFloat(s.opacity)<.05)return;const r=e.getBoundingClientRect();if(r.width<8||r.height<8)return;
const inH=r.top<hh&&r.bottom>0, inD=r.bottom>innerHeight-dh&&r.top<innerHeight;out.push([e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+'.'+(e.className&&e.className.baseVal===undefined?String(e.className).split(' ')[0]:''),Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height),s.position,s.zIndex,inH?'HEAD':'',inD?'DOCK':''].join(' '))});return {hh,dh,out}}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        for pn in ["photo","cinema"]:
            for w,h in [(1440,900),(390,844)]:
                pg=await (await b.new_context(viewport={"width":w,"height":h})).new_page()
                await pg.goto("http://127.0.0.1:8091/web/%s.html"%pn,wait_until="domcontentloaded",timeout=60000); await pg.wait_for_timeout(5000)
                r=await pg.evaluate(JS); print("##",pn,w,"head",r['hh'],"dock",r['dh'])
                for l in r['out']: print("  ",l)
asyncio.run(main())
PYEOF
$PY /tmp/s6_o1.py 2>&1 | tail -90
