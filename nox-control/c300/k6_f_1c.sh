echo "C300: k6_f_1c"
S=/workspace/nox/web/site; cd $S
python3 - <<'PY'
p='nox-k6-dash.js';s=open(p,encoding='utf-8').read()
s=s.replace("grid.engine.nodes.map(function(n){return{t:n.el.querySelector('[data-k6]').dataset.k6,x:n.x,y:n.y,w:n.w,h:n.h}})","grid.engine.nodes.filter(function(n){return n.el&&n.el.querySelector('[data-k6]')}).map(function(n){return{t:n.el.querySelector('[data-k6]').dataset.k6,x:n.x,y:n.y,w:n.w,h:n.h}})")
open(p,'w',encoding='utf-8').write(s)
p='nox-k6-karaoke.js';s=open(p,encoding='utf-8').read()
s=s.replace("au.insertAdjacentElement('afterend',bar);","const vis=function(e){return e&&e.getBoundingClientRect().height>0};if(vis(au))au.insertAdjacentElement('afterend',bar);else{const h=['mu','muRoot','page'].map(function(i){return document.getElementById(i)}).filter(vis)[0]||document.body;h.insertBefore(bar,h.firstChild)}")
open(p,'w',encoding='utf-8').write(s)
PY
grep -c "filter(function(n){return n.el" nox-k6-dash.js; grep -c "const vis" nox-k6-karaoke.js
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 200 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
C=[
("system","""(async()=>{await new Promise(r=>setTimeout(r,1500));await K6dash.open();await new Promise(r=>setTimeout(r,2000));const a=K6dash.count();K6dash.add('num');await new Promise(r=>setTimeout(r,500));const d=document.getElementById('k6-dash-d');const bb=[...d.querySelectorAll('button[data-a]')].map(b=>b.getBoundingClientRect().height);return JSON.stringify({a,b:K6dash.count(),chart:!!d.querySelector('canvas,svg'),tb:!!d.querySelector('.k6-tb'),minbtn:Math.min(...bb),ls:localStorage.getItem('nox.k6.dash.v1').length})})()"""),
("music","""(async()=>{await new Promise(r=>setTimeout(r,1500));await K6kar.setVocal(0);await new Promise(r=>setTimeout(r,500));const s=K6kar.state();const r=document.getElementById('k6-kr').getBoundingClientRect();return JSON.stringify({s,h:r.height,w:r.width,txt:document.getElementById('k6-kv').textContent})})()"""),
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
echo "K6 f_1c done"
