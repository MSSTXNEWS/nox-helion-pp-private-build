echo "C300: th_dep_gr2b (логотип NOX, иконки Lucide, карта цветов, nox-theme на operators/live)"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
SHA=065864ef23c92199a6d16e73ba15a72adec110f5
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$SHA/nox-control/c300/bundles/th_graphite
G=/tmp/th_gr2; rm -rf $G; mkdir -p $G
for f in nox-graphite.css nox-theme.js nox-icons.js nox-logo.svg lucide.zip patch.py th_gen_map.py; do curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/$f -o $G/$f && [ -s $G/$f ] || { echo "FAIL fetch $f"; exit 0; }; done
node --check $G/nox-theme.js && node --check $G/nox-icons.js || { echo FAIL_SYNTAX; exit 0; }
for f in nox-theme.js nox-graphite.css nox-graphite-map.css nox-nav.js nox-wow.js operators.html live.html; do [ -f $f ] && cp $f $f.bak_th2_$TS; done
echo "$TS" > /workspace/nox/web/th_gr2.ts
cp $G/nox-graphite.css $G/nox-theme.js $G/nox-icons.js $G/nox-logo.svg .
mkdir -p vendor/lucide && $PY -c "import zipfile;zipfile.ZipFile('$G/lucide.zip').extractall('vendor/lucide')" && ls vendor/lucide/icons | wc -l
$PY $G/patch.py $S
for f in nox-nav.js nox-wow.js; do node --check $f 2>/dev/null || { echo "SYNTAX $f -> restore"; cp $f.bak_th2_$TS $f; }; done
$PY $G/th_gen_map.py $S $S/nox-graphite-map.css
cat > /tmp/th_qa2.py <<'PEOF'
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
    await b.close()
  print('QABAD',bad)
asyncio.run(m())
PEOF
timeout 175 $PY /tmp/th_qa2.py | tee /tmp/th_qa2.out
if ! grep -q "QABAD 0" /tmp/th_qa2.out; then
  echo ROLLBACK; for f in nox-theme.js nox-graphite.css nox-graphite-map.css nox-nav.js nox-wow.js operators.html live.html; do [ -f $f.bak_th2_$TS ] && cp $f.bak_th2_$TS $f; done
else echo QA_CLEAN; fi
echo done
