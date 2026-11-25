echo "C300: u_big1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
echo "== A. index state"; grep -c "nox-k8-live.js" index.html; tail -3 /tmp/u_qa_idx.txt 2>/dev/null | cut -c1-300
echo "== B. probes"
W=/workspace/nox/web/pkg/server/web_server.py
grep -n '"/svc/\|/svc/advisors\|vision/describe\|/img/generate' $W | cut -c1-200 | head -12
sed -n '/def _img_generate/,/^    def /p' $W | head -40 | cut -c1-220
echo "-- img/generate live"; timeout 90 curl -s -m 85 -X POST localhost:8091/img/generate -H 'Content-Type: application/json' -d '{"prompt":"red apple on table","width":256,"height":256,"steps":4}' | head -c 600; echo
echo "-- vision/describe live"; PNG=iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==
timeout 60 curl -s -m 55 -X POST localhost:8091/vision/describe -H 'Content-Type: application/json' -d "{\"image\":\"data:image/png;base64,$PNG\",\"prompt\":\"Что на картинке? Ответ: ОЦЕНКА: N/10\"}" | head -c 600; echo
echo "-- svc advisors"; for p in /svc/advisors/v1/models /svc/advisors/health /svc/advisors/draft; do echo "$p $(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091$p)"; done
curl -s -m 5 localhost:8793/v1/models | head -c 900; echo
echo "== C. patch draw.js"
cp nox-k8-draw.js nox-k8-draw.js.bak_u_$TS
cat > /tmp/u_patch_draw.py <<'PYEOF'
import re,sys
f='nox-k8-draw.js';s=open(f,encoding='utf-8').read()
if 'U_PATCH1' in s: print('already');sys.exit()
a=s.index(" const PRE=[");b=s.index("\n",a)
s=s[:a]+" const PRE=['plastic skin, waxy, airbrushed','extra fingers, fused fingers, missing fingers','deformed hands, malformed limbs','asymmetrical eyes, cross-eyed','blurry, out of focus','lowres, jpeg artifacts','oversaturated, overexposed, HDR look','cartoon, 3d render, cgi, illustration','text, watermark, logo, signature','duplicate, cloned face, extra head','bad anatomy, bad proportions','uncanny, doll-like, mannequin','oversharpened, halo','cropped, cut off head']; /* U_PATCH1 PHOTOREAL100 анти-настройки */"+s[b:]
old="else run(t,3)});return d}"
assert old in s
s=s.replace(old,"else run(t,3)});try{if(window.NOXGhost){NOXGhost.attach(pos,{page:'creative-positive'});NOXGhost.attach(ng,{page:'creative-negative'})}}catch(e){}return d}")
old2="if(its.length)choose(prompt,its);return its}"
assert old2 in s
new2="""const best=its.reduce(function(m,x){return Math.max(m,x.score==null?-1:x.score)},-1);
  if(best<6&&!(sig&&sig.aborted)){const su=await senior.gen(prompt,sig);if(su){const c2=await senior.critic(su,prompt,sig);its.push({u:su,score:c2&&c2.score!=null?c2.score:null,errors:(c2&&c2.errors)||'',p:prompt,senior:1});S&&S.post({t:'Локальный результат слабый ('+best+'/10): сгенерировал старший советник'+(c2&&c2.score!=null?' · оценка '+c2.score+'/10':''),img:su,ts:Date.now()})}}
  if(its.length)choose(prompt,its);return its}"""
s=s.replace(old2,new2)
sen=""" /* старшие советники по рисованию: шлюз :8793 (drawing_senior_gen/_critic) через /svc/advisors/*; нет маршрута или 403 -> молча null */
 const senior={ok:null,
  async post(path,body,sig){try{const r=await fetch('/svc/advisors/v1/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:sig});if(!r.ok)return null;return await r.json()}catch(e){return null}},
  async gen(prompt,sig){const j=await senior.post('images/generations',{prompt:prompt,size:'768x768',response_format:'b64_json'},sig);const b=j&&j.data&&j.data[0]&&j.data[0].b64_json;return b?'data:image/png;base64,'+b:null},
  async critic(u,prompt,sig){const j=await senior.post('images/critique',{image_b64:u,prompt:prompt},sig);if(!j)return null;const c=j.critique||{};const sc=c.score!=null?+c.score:(c.rating!=null?+c.rating:null);const t=j.text||'';const m=sc==null&&/(\\d+(?:[.,]\\d+)?)\\s*\\/\\s*10/.exec(t);return{score:sc!=null?sc:(m?parseFloat(m[1].replace(',','.')):null),errors:String(c.errors||c.issues||c.problems||'').slice(0,200),text:t.slice(0,300)}}};
"""
s=s.replace(" async function run(prompt",sen+" async function run(prompt",1)
s=s.replace("window.K8draw={run:run,","window.K8draw={senior:senior,run:run,")
open(f,'w',encoding='utf-8').write(s);print('patched')
PYEOF
python3 /tmp/u_patch_draw.py && node --check nox-k8-draw.js && echo SYNTAX_OK || { cp nox-k8-draw.js.bak_u_$TS nox-k8-draw.js; echo ROLLBACK_SYNTAX; }
sed -i 's#nox-k8-draw.js?v=[a-z0-9]*#nox-k8-draw.js?v=u1#' creative.html; grep -c "draw.js?v=u1" creative.html
echo "U: ghost в позитиве/негативе, пресеты негатива PHOTOREAL100, старшие советники (fallback)" >> qa/rework/creative.fixed
echo "== D. background QA"
cat > /tmp/u_qa1.sh <<'QEOF'

for i in $(seq 1 6); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/web/index.html); [ "$c" = 200 ] && break; sleep 10; done
echo "http $c"
if [ "$c" != 200 ]; then bash /workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -3; sleep 12; echo "http $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/web/index.html)"; fi
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
echo "K8 qa1 done"
QEOF
cat > /tmp/u_mqa.py <<'MEOF'
import asyncio,json,base64,sys,os
from playwright.async_api import async_playwright
nav=json.load(open('/workspace/nox/web/site/nav.json'))
pages=['index']+[i['file'][:-5] for g in nav['groups'] for i in g['items']]
if os.environ.get('PAGES'): pages=os.environ['PAGES'].split(',')
W=[int(x) for x in os.environ.get('WIDTHS','390').split(',')]
SHOT=os.environ.get('SHOTS','').split(',')
JS="""()=>{const w=innerWidth,r={};const tab=document.querySelector('#nox-m-tab');r.tab=!!tab;
const tb=tab?tab.getBoundingClientRect():null;
r.sw=document.documentElement.scrollWidth;
const q='a,button,[role=button],[role=tab],input:not([type=hidden]),select,summary,sl-button,sl-icon-button,sl-tab';
r.small=[];document.querySelectorAll(q).forEach(e=>{if(e.closest('#nxdock'))return;const b=e.getBoundingClientRect();const s=getComputedStyle(e);if(!b.width||!b.height||s.visibility==='hidden'||s.opacity==='0'||b.left<-50||b.top>innerHeight*3)return;if(e.offsetParent===null&&s.position!=='fixed')return;if(b.width<43.5||b.height<43.5)r.small.push((e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+' '+Math.round(b.width)+'x'+Math.round(b.height)+' '+(e.innerText||'').slice(0,12).replace(/\\n/g,' ')))});
r.font=0;const wk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;const seen=new Set();r.fontEx=[];while((n=wk.nextNode())){if(!n.nodeValue.trim())continue;const e=n.parentElement;if(!e||seen.has(e)||e.closest('script,style,svg,canvas,#nxdock'))continue;seen.add(e);const b=e.getBoundingClientRect();if(!b.width||!b.height||getComputedStyle(e).visibility==='hidden')continue;const fz=parseFloat(getComputedStyle(e).fontSize);if(fz>=1&&fz<13.9){r.font++;if(r.fontEx.length<2)r.fontEx.push(e.tagName+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+getComputedStyle(e).fontSize)}}
r.wide=[];document.querySelectorAll('body *').forEach(e=>{if(e.closest('#nxdock'))return;const b=e.getBoundingClientRect();const s=getComputedStyle(e);if(s.position==='fixed'||!b.width||s.visibility==='hidden')return;if(b.right>w+2&&b.left>=-2){let p=e.parentElement,sc=false;while(p&&p!==document.body){const o=getComputedStyle(p).overflowX;if((o==='auto'||o==='scroll'||o==='hidden')&&p.getBoundingClientRect().right<=w+2){sc=true;break}p=p.parentElement}if(!sc&&r.wide.length<4)r.wide.push(e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+' r'+Math.round(b.right))}});
r.ovl=[];if(tb){document.querySelectorAll('body *').forEach(e=>{if(e.closest('#nox-m-tab,#nox-m-ai,.nox-m-sheet,#nox-m-scrim'))return;const s=getComputedStyle(e);if(s.position!=='fixed'||s.opacity==='0'||s.pointerEvents==='none')return;const b=e.getBoundingClientRect();if(b.width>300&&b.height>600)return;if(b.width<2)return;if(b.bottom>tb.top+2&&b.top<tb.bottom&&b.right>0&&b.left<w)r.ovl.push(e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:''))});
const sun=document.querySelector('#nxsun');if(sun){const b=sun.getBoundingClientRect();r.sunY=Math.round(b.bottom)}}
return r}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w in W:
            for pg in pages:
                c=await b.new_page(viewport={"width":w,"height":844 if w<500 else 1024})
                errs=[]
                c.on('pageerror',lambda e:errs.append(str(e)[:100]))
                try:
                    for t in range(3):
                        try: await c.goto("http://127.0.0.1:8091/web/%s.html"%pg,wait_until="load",timeout=25000);break
                        except Exception as e:
                            if t==2: raise
                            await asyncio.sleep(3)
                    await c.wait_for_timeout(int(os.environ.get('WAIT','3500')))
                    r=await c.evaluate(JS)
                    bad=len(errs)+(1 if r['sw']>w else 0)+len(r['small'])+len(r['ovl'])+len(r['wide'])
                    print("OUT: %d %-14s js%d sw%d tab%d small%d font%d wide%d ovl%d %s"%(w,pg,len(errs),r['sw'],r['tab'],len(r['small']),r['font'],len(r['wide']),len(r['ovl']),"OK" if not bad and not r['font'] else "!!"))
                    if bad or r['font']:
                        print("OUT:    ",errs[:2],r['small'][:5],r['wide'][:3],r['ovl'][:3],r['fontEx'])
                    if pg in SHOT:
                        await c.screenshot(path="/tmp/m_%s_%d.jpg"%(pg,w),type="jpeg",quality=38)
                        print("B64_%s%d_BEGIN"%(pg,w));print(base64.b64encode(open("/tmp/m_%s_%d.jpg"%(pg,w),'rb').read()).decode());print("B64_%s%d_END"%(pg,w))
                        if os.environ.get('SHEET'):
                            for tag,sel in (('more','#nox-m-more'),('cmd','a[href="#cmd"]')):
                                if await c.query_selector(sel):
                                    await c.click(sel);await c.wait_for_timeout(900)
                                    await c.screenshot(path="/tmp/m_s.jpg",type="jpeg",quality=38)
                                    print("B64_%s%s%d_BEGIN"%(pg,tag,w));print(base64.b64encode(open("/tmp/m_s.jpg",'rb').read()).decode());print("B64_%s%s%d_END"%(pg,tag,w))
                                    await c.keyboard.press('Escape');await c.mouse.click(200,60);await c.wait_for_timeout(400)
                except Exception as e: print("OUT: %d %s FAIL %s"%(w,pg,str(e)[:100]))
                await c.close()
        await b.close()
asyncio.run(main())
MEOF
cat > /tmp/u_cr.py <<'CEOF'
import asyncio
from playwright.async_api import async_playwright
JS="""(async()=>{const o={};o.draw=typeof K8draw;o.pre=K8draw.presets.length;o.sen=typeof K8draw.senior.gen;o.ghost=typeof window.NOXGhost;K4.fab;document.getElementById('k8-prompt-b')&&document.getElementById('k8-prompt-b').click();await new Promise(r=>setTimeout(r,1200));o.pos=!!document.getElementById('k8-pos');o.chips=document.querySelectorAll('#k8-chips button').length;o.sg=await K8draw.senior.gen('x');return JSON.stringify(o)})()"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
      try:
        await pg.goto('http://127.0.0.1:8091/web/creative.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.K8draw',timeout=15000);await pg.wait_for_timeout(1500)
        print('QA',w,await asyncio.wait_for(pg.evaluate(JS),40),'errs',errs[:3])
      except Exception as e: print('QA EXC',w,str(e)[:200],errs[:3])
      await pg.close()
    await b.close()
asyncio.run(m())
CEOF
timeout 120 $PY /tmp/u_cr.py | tee /tmp/u_cr.out
if grep -q "EXC\|errs \['" /tmp/u_cr.out; then cp nox-k8-draw.js.bak_u_$TS nox-k8-draw.js; echo ROLLBACK_DRAW; fi
nohup bash -c "cd $S; PAGES=system,widgets,training,chat,assistant,finance WIDTHS=430,768 WAIT=3500 $PY /tmp/u_mqa.py > /tmp/u_mqa.out 2>&1; bash /tmp/u_qa1.sh > /tmp/u_qa1.out 2>&1; echo FIN >> /tmp/u_qa1.out" > /dev/null 2>&1 &
echo "bg started"; echo "u_big1 done"
