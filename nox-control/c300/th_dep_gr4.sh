echo "C300: th_dep_gr4 (дубли кнопок s6h, единый primary, бейджи, переводы Filerobot локально)"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
SHA=ecd14f85b701cbeae254ae6fc64fe1fa40081fb0
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$SHA/nox-control/c300/bundles/th_graphite
G=/tmp/th_gr4; rm -rf $G; mkdir -p $G
for f in nox-graphite.css nox-th-fix.css nox-theme.js patch.py th_gen_map.py fie-i18n.json; do curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/$f -o $G/$f && [ -s $G/$f ] || { echo "FAIL fetch $f"; exit 0; }; done
node --check $G/nox-theme.js || { echo FAIL_SYNTAX; exit 0; }
for f in nox-theme.js nox-graphite.css nox-graphite-map.css nox-th-fix.css vendor/nox-x/filerobot/filerobot-image-editor.min.js; do [ -f $f ] && cp $f $f.bak_th4_$TS; done
echo "$TS" > /workspace/nox/web/th_gr4.ts
cp $G/nox-graphite.css $G/nox-th-fix.css $G/nox-theme.js .
cp $G/fie-i18n.json vendor/nox-x/filerobot/fie-i18n.json
$PY $G/patch.py $S
$PY $G/th_gen_map.py $S $S/nox-graphite-map.css
cat > /tmp/th_qa4.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  bad=0
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('index','chat','settings','system','music','news','creative','photo','operators'):
      for w,h in ((1440,900),(390,844)):
        c=await b.new_page(viewport={'width':w,'height':h});errs=[];fails=[]
        c.on('pageerror',lambda e:errs.append(str(e)[:100]));c.on('response',lambda r:fails.append(r.url[-60:]) if r.status>=400 and r.url.endswith('.svg') else None)
        try:
          await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=25000);await c.wait_for_timeout(4500)
          r=await c.evaluate("[document.documentElement.getAttribute('data-nox-theme'),!!document.querySelector('link[data-nox-graphite]'),window.NOXiconSet||'',[...document.querySelectorAll('sl-icon')].filter(e=>e.getBoundingClientRect().width>0&&!(e.shadowRoot&&e.shadowRoot.querySelector('svg'))).length]")
          if w==1440 and pg in ('index','chat'): await c.screenshot(path='/workspace/nox/agent/out/th2_%s_1440.jpg'%pg,type='jpeg',quality=72)
        except Exception as e: r=['EXC',0,'',0];errs.append(str(e)[:80])
        bad_e=[e for e in errs if 'Graphite' in e or 'NOXtheme' in e or 'nox-theme' in e or 'NOXicon' in e]
        print('QA',pg,w,r,'svg404',fails[:3],errs[:2],flush=True)
        if r[0]!='graphite' or not r[1] or r[2]!='lucide' or bad_e: bad+=1
        await c.close()
    c=await b.new_page(viewport={'width':1440,'height':900});await c.goto('http://127.0.0.1:8091/web/news.html',wait_until='domcontentloaded');await c.wait_for_timeout(4000)
    n=await c.evaluate("[...document.querySelectorAll('.s6h')].filter(e=>e.getBoundingClientRect().width>0).length");print('QAS6H',n)
    if n>0: bad+=1
    c=await b.new_page(viewport={'width':2560,'height':1440});await c.goto('http://127.0.0.1:8091/web/index.html',wait_until='domcontentloaded');await c.wait_for_timeout(4500)
    r=await c.evaluate("(()=>{const w=document.querySelector('.wrap').getBoundingClientRect();return [Math.round(w.x),Math.round(w.width),innerWidth]})()");print('QA4K',r)
    await c.screenshot(path='/workspace/nox/agent/out/th3_index_2560.jpg',type='jpeg',quality=72)
    if r[0]<0 or r[0]+r[1]>r[2]+2: bad+=1
    await b.close()
  print('QABAD',bad)
asyncio.run(m())
PEOF
timeout 175 $PY /tmp/th_qa4.py | tee /tmp/th_qa4.out
if ! grep -q "QABAD 0" /tmp/th_qa4.out && ! grep -q 'graphite\] button{' $S/nox-graphite-map.css; then
  echo ROLLBACK; for f in nox-theme.js nox-graphite.css nox-graphite-map.css nox-th-fix.css vendor/nox-x/filerobot/filerobot-image-editor.min.js; do [ -f $f.bak_th4_$TS ] && cp $f.bak_th4_$TS $f; done; rm -f vendor/nox-x/filerobot/fie-i18n.json
else echo QA_CLEAN; fi
echo done
