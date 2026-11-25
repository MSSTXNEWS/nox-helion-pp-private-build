echo "C300: k6_f_1d"
S=/workspace/nox/web/site; cd $S
python3 - <<'PY'
p='nox-k6-dash.js';s=open(p,encoding='utf-8').read()
old="grid.addWidget({x:o.x,y:o.y,w:o.w||4,h:o.h||3,content:'<div data-k6=\"'+t+'\" style=\"width:100%;height:100%\"></div>'});render();save()}"
new="const el=document.createElement('div');el.className='grid-stack-item';el.innerHTML='<div class=\"grid-stack-item-content\"><div data-k6=\"'+t+'\" style=\"width:100%;height:100%\"></div></div>';grid.addWidget(el,{x:o.x,y:o.y,w:o.w||4,h:o.h||3});render();save()}"
print(old in s); s=s.replace(old,new);open(p,'w',encoding='utf-8').write(s)
PY
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 200 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
C=[
("system","""(async()=>{await new Promise(r=>setTimeout(r,1500));await K6dash.open();await new Promise(r=>setTimeout(r,2500));const a=K6dash.count();K6dash.add('num');await new Promise(r=>setTimeout(r,500));const d=document.getElementById('k6-dash-d');return JSON.stringify({a,b:K6dash.count(),chart:!!d.querySelector('canvas,svg'),tb:!!d.querySelector('.k6-tb'),ls:localStorage.getItem('nox.k6.dash.v1').length,ec:!!window.echarts,gs:typeof GridStack})})()"""),
("music","""(async()=>{await new Promise(r=>setTimeout(r,1500));const bar=document.getElementById('k6-kar');let o=[];let e=bar;while(e&&o.length<8){const c=getComputedStyle(e);o.push(e.tagName+'#'+e.id+':'+c.display+'/'+c.visibility+'/'+Math.round(e.getBoundingClientRect().height));e=e.parentElement}return JSON.stringify({o,au:document.getElementById('mAud').getBoundingClientRect().height,kids:[...document.body.children].map(x=>x.tagName+'#'+x.id+Math.round(x.getBoundingClientRect().height)).slice(0,14)})})()"""),
]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
    for w,h in((1440,900),):
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
echo "K6 f_1d done"
