echo "C300: k6_f_1b"
S=/workspace/nox/web/site; cd $S
ls -la nox-k6-* | awk '{print $5,$9}'; grep -c "nox-k6-" chat.html system.html knowledge.html pdf.html music.html; tail -2 qa/rework/chat.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 240 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
C=[
("chat","""(async()=>{await new Promise(r=>setTimeout(r,1500));const t=document.getElementById('input');t.focus();t.value='привет @';t.setSelectionRange(8,8);t.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,300));const p=document.getElementById('k6-mn');const n=p?p.querySelectorAll('button').length:0;const h=p?Math.min(...[...p.querySelectorAll('button')].map(b=>b.getBoundingClientRect().height)):0;p.querySelector('button').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));const v=t.value;const c=K6mention.compose(v);return JSON.stringify({n,h,v,ok:c.includes('Контекст упоминаний')})})()"""),
("system","""(async()=>{await new Promise(r=>setTimeout(r,1500));document.querySelector('#k4-fab [data-id=k6-dash],#k4-fab button').click();K6dash.open&&0;await K6dash.open();await new Promise(r=>setTimeout(r,1500));const a=K6dash.count();K6dash.add('num');await new Promise(r=>setTimeout(r,500));const d=document.getElementById('k6-dash-d');return JSON.stringify({a,b:K6dash.count(),chart:!!d.querySelector('canvas,svg'),tb:!!d.querySelector('.k6-tb')})})()"""),
("knowledge","""(async()=>{await new Promise(r=>setTimeout(r,1500));await K6map.build('Космос');const a=K6map.count();return JSON.stringify({a})})()"""),
("pdf","""(async()=>{await new Promise(r=>setTimeout(r,1500));const n=await K6slides.make('Введение\\nЭто первый абзац. Он важен.\\n\\nГлава два\\nВторой абзац. Детали тут.\\n\\nИтог\\nКонец. Спасибо.');await new Promise(r=>setTimeout(r,500));return JSON.stringify({n,t:K6slides.count(),sec:document.querySelectorAll('#k6-rv section').length,sp:!!window.speechSynthesis})})()"""),
("music","""(async()=>{await new Promise(r=>setTimeout(r,1500));await K6kar.setVocal(0);await new Promise(r=>setTimeout(r,500));const s=K6kar.state();const b=document.getElementById('k6-kr').getBoundingClientRect().height;return JSON.stringify({s,b,txt:document.getElementById('k6-kv').textContent})})()"""),
]
async def m():
  import sys
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
    for w,h in((1440,900),(390,844)):
      for u,js in C:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(2500);r=await asyncio.wait_for(pg.evaluate(js),25)
        except Exception as e: r='EXC '+str(e)[:200]
        print('QA',w,u,r,'errs',len(errs),errs[:2]);
        try: await asyncio.wait_for(pg.close(),5)
        except Exception: pass
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 f_1 done"
