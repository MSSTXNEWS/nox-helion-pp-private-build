echo "C300: k8_pr_6"
S=/workspace/nox/web/site; cd $S
echo "http $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/web/index.html)"
for p in design settings; do echo "--PG $p"; wc -c $p.html; grep -o '<script[^>]*src="[^"]*"' $p.html | sed 's/<script[^>]*src=//' | tr '\n' ' ' | head -c 900; echo; grep -o 'id="[^"]*"' $p.html | head -70 | tr '\n' ' '; echo; done
ls | grep -i "design\|creative\|nox-dz\|persona" | head -20
ls vendor/img-comparison-slider vendor/painterro vendor/split.js vendor/gridstack vendor/canvas-confetti 2>&1 | head -20
ls /workspace/nox/state 2>&1 | head; ls /workspace/nox/state/persona.json 2>&1
curl -s -m 5 -o /dev/null -w "8104 %{http_code}\n" http://127.0.0.1:8104/health
grep -n "meta\.\(emo\|sources\)" -r nox-ai-s1.js nox-k3-core.js 2>/dev/null | head -3 | cut -c1-200
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 260 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
MB="Math.min(...[...document.querySelectorAll('%s button,%s input')].filter(x=>x.offsetParent!==null&&x.getBoundingClientRect().height>0).map(x=>Math.round(x.getBoundingClientRect().height)))"
T={'training':('K8anki',"""(async()=>{const o={};await K8anki.open();await new Promise(r=>setTimeout(r,500));o.s=await K8anki.stats();o.rev=K8anki.reveal();o.iv=K8anki.intervals();o.rate=await K8anki.rate(3);o.s2=await K8anki.stats();o.minh=%s;return JSON.stringify(o)})()""" % (MB%('#k8-anki-d','#k8-anki-d'))),
 'finance':('K8budget',"""(async()=>{const o={};await K8budget.open();K8budget.setLimit(30000);K8budget.add(1500,'тест');K8budget.add(900,'тест2');o.st=K8budget.stat();o.ans=K8budget.answer('сколько осталось');o.minh=%s;
 await K8annot.open();await new Promise(r=>setTimeout(r,900));K8annot.add(new Date().toISOString().slice(0,10),'событие');o.mk=K8annot.marks().length;o.chart=!!(K8annot.chart()&&K8annot.chart().getOption);
 const e=document.getElementById('fiMain')||document.body;const t=document.createElement('span');t.id='k8t';t.textContent='100';e.appendChild(t);K8tick.scan();t.textContent='250';K8tick.scan();o.tickcls=t.className;await new Promise(r=>setTimeout(r,1000));o.tick=t.textContent;t.remove();return JSON.stringify(o)})()""" % (MB%('#k8-budget-d','#k8-budget-d'))),
 'atlas':('K8night',"""(async()=>{const o={};await K8night.open();await new Promise(r=>setTimeout(r,600));o.a=K8night.draw(0);o.b=K8night.draw(12);o.minh=%s;return JSON.stringify(o)})()""" % (MB%('#k8-night-d','#k8-night-d'))),
 'index':('K7cards',"""(async()=>{const o={};await K7cards.open();await new Promise(r=>setTimeout(r,1500));const c=document.querySelectorAll('#k7-cs .k7-card').length;o.cards=c;const a=window.K8embla&&K8embla.api();o.embla=!!a;if(a){o.slides=a.slideNodes().length;try{a.scrollNext()}catch(e){}}
 const f=await K7find.search('новост');o.find=f.length;const g=await K7find.search('нвости');o.fuzzy=g.length;return JSON.stringify(o)})()""")}
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for pg_ in ('training','finance','atlas','index'):
        if pg_=='index' and w==390: continue
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/%s.html'%pg_,wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.%s'%T[pg_][0],timeout=15000);await pg.wait_for_timeout(1500)
          r=await asyncio.wait_for(pg.evaluate(T[pg_][1]),50);print('QA',w,pg_,r,'errs',errs[:3])
        except Exception as e: print('QA EXC',w,pg_,str(e)[:300],errs[:3])
        await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
echo "K8 pr6 done"
