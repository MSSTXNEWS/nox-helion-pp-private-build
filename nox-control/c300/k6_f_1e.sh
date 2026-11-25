echo "C300: k6_f_1e"
S=/workspace/nox/web/site; cd $S
python3 - <<'PY'
p='nox-k6-karaoke.js';s=open(p,encoding='utf-8').read()
a='<input type="range" id="k6-kr" min="0" max="100" value="100" aria-label="Громкость вокала">'
b="'+(customElements.get('sl-range')?'<sl-range id=\"k6-kr\" min=\"0\" max=\"100\" value=\"100\" label=\"Громкость вокала\"></sl-range>':'<input type=\"range\" id=\"k6-kr\" min=\"0\" max=\"100\" value=\"100\" aria-label=\"Громкость вокала\">')+'"
print(a in s);s=s.replace(a,b)
s=s.replace("rg.addEventListener('input',function(){setVocal(rg.value/100)});","const on1=function(){setVocal(rg.value/100)};rg.addEventListener('input',on1);rg.addEventListener('sl-input',on1);")
open(p,'w',encoding='utf-8').write(s)
c=open('nox-k6-ui.css',encoding='utf-8').read()
if 'sl-range' not in c: open('nox-k6-ui.css','a',encoding='utf-8').write('.k6-kar sl-range{flex:1;min-width:140px;min-height:44px;display:flex;align-items:center}\n')
PY
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 220 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
C=[
("music","""(async()=>{await new Promise(r=>setTimeout(r,1500));const r0=document.getElementById('k6-kr');r0.value=0;r0.dispatchEvent(new Event('sl-input'));await new Promise(r=>setTimeout(r,600));const s=K6kar.state();const r=r0.getBoundingClientRect();return JSON.stringify({tag:r0.tagName,s,h:r.height,w:r.width,txt:document.getElementById('k6-kv').textContent})})()"""),
]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
    for w,h in((1440,900),(390,844)):
      for u,js in C:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(2500);r=await asyncio.wait_for(pg.evaluate(js),25)
        except Exception as e: r='EXC '+str(e)[:200]
        print('QA',w,u,r,'errs',len(errs),errs[:2])
        try: await asyncio.wait_for(pg.close(),5)
        except Exception: pass
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 f_1e done"
