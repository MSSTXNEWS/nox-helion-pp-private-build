echo "C300: k6_f_2c"
S=/workspace/nox/web/site; cd $S
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 270 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
W="await new Promise(r=>setTimeout(r,1500));"
C=[
("index",W+"""await K6split.open('chat','memory');await new Promise(r=>setTimeout(r,1200));const sel=document.querySelectorAll('#k6-sp-d select');return JSON.stringify({n:K6split.count(),s:K6split.srcs(),h:Math.min(...[...sel].map(x=>x.getBoundingClientRect().height))})"""),
("memory",W+"""const n=await K6links.build('Проект NOX память заметки график',['NOX проект график связи','Погода сегодня','заметки память проект','Другое совсем']);await K6board.add('Идея А');const b=await K6board.add('Идея Б');K6board.link('c1','c2');await new Promise(r=>setTimeout(r,500));return JSON.stringify({n,nodes:K6links.count(),cards:K6board.count(),edges:K6board.edges()})"""),
("studio",W+"""const h=await K6live.build('форма: имя, email, сообщение');await new Promise(r=>setTimeout(r,800));return JSON.stringify({form:/<form/.test(h),sb:K6live.sandbox(),fr:K6live.html().length>50})"""),
("assistant_x",W+"""await K6canvas.set('Первый абзац\\nВторой абзац');await new Promise(r=>setTimeout(r,600));K6canvas.focusFirst();K6canvas.replace('Новый текст');await new Promise(r=>setTimeout(r,400));return JSON.stringify({t:K6canvas.text()})"""),
("system_x",W+"""await K6dash.open();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({n:K6dash.count()})"""),
]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for u,js in C:
        if u.endswith('_x'): continue
        gl={'index':'K6split','memory':'K6links','studio':'K6live'}[u]
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.'+gl,timeout=15000);r=await asyncio.wait_for(pg.evaluate("(async()=>{"+js+"})()"),45)
        except Exception as e: r='EXC '+str(e)[:240]
        print('QA',w,u,r,'errs',len(errs),errs[:2])
        try: await asyncio.wait_for(pg.close(),5)
        except Exception: pass
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 f_2c done"
