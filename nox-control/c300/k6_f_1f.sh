echo "C300: k6_f_1f"
S=/workspace/nox/web/site; cd $S
python3 - <<'PY'
p='nox-k6-karaoke.js';s=open(p,encoding='utf-8').read()
s=s.replace('<input type=\\"range\\" id=\\"k6-kr\\"','<input type=\\"range\\" style=\\"display:block!important;visibility:visible!important;opacity:1!important;flex:1;min-width:140px;height:44px;width:auto\\" id=\\"k6-kr\\"')
open(p,'w',encoding='utf-8').write(s);print('style' in s, s.count('display:block!important'))
PY
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 220 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
JS="""(async()=>{await new Promise(r=>setTimeout(r,1500));const r0=document.getElementById('k6-kr');r0.value=30;r0.dispatchEvent(new Event('input'));await new Promise(r=>setTimeout(r,600));const s=K6kar.state();const r=r0.getBoundingClientRect();const c=getComputedStyle(r0);const b=document.getElementById('k6-kt').getBoundingClientRect();return JSON.stringify({s,h:r.height,w:r.width,disp:c.display,bh:b.height,txt:document.getElementById('k6-kv').textContent})})()"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
    for w,h in((1440,900),(390,844)):
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/music.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(2500);r=await asyncio.wait_for(pg.evaluate(JS),25)
        except Exception as e: r='EXC '+str(e)[:200]
        print('QA',w,r,'errs',len(errs),errs[:2])
        try: await asyncio.wait_for(pg.close(),5)
        except Exception: pass
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 f_1f done"
