echo "C300: th_dep_gr1 (тема Графит + кнопки)"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
SHA=f7442f496012df400ab1b8802eda0dfca05e911b
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$SHA/nox-control/c300/bundles/th_graphite
G=/tmp/th_gr1; rm -rf $G; mkdir -p $G
for f in nox-graphite.css nox-theme.js patch.py th_gen_map.py; do curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/$f -o $G/$f && [ -s $G/$f ] || { echo "FAIL fetch $f"; exit 0; }; done
node --check $G/nox-theme.js || { echo FAIL_SYNTAX; exit 0; }
grep -q "TH-GRAPHITE" $G/nox-theme.js || echo marker_ok
for f in nox-theme.js nox-wow-bg.js nox-ds.js nox-actions.js; do [ -f $f ] && cp $f $f.bak_th_$TS; done
echo "$TS" > /workspace/nox/web/th_gr1.ts
cp $G/nox-graphite.css nox-graphite.css; cp $G/nox-theme.js nox-theme.js
$PY $G/patch.py $S
for f in nox-wow-bg.js nox-ds.js nox-actions.js; do node --check $f 2>/dev/null || { echo "SYNTAX $f -> restore"; cp $f.bak_th_$TS $f; }; done
$PY $G/th_gen_map.py $S $S/nox-graphite-map.css
cat > /tmp/th_qa.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  bad=0
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('index','chat','settings','system','music','news','creative','photo'):
      for w,h in ((1440,900),(390,844)):
        c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
        try:
          await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=25000);await c.wait_for_timeout(3500)
          r=await c.evaluate("[document.documentElement.getAttribute('data-nox-theme'),!!document.querySelector('link[data-nox-graphite]'),getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()]")
          if w==1440 and pg in ('index','chat'): await c.screenshot(path='/workspace/nox/agent/out/th_%s_1440.jpg'%pg,type='jpeg',quality=72)
        except Exception as e: r=['EXC'];errs.append(str(e)[:80])
        bad_e=[e for e in errs if 'Graphite' in e or 'NOXtheme' in e or 'nox-theme' in e]
        print('QA',pg,w,r,errs[:2],flush=True)
        if r[0]!='graphite' or not r[1] or bad_e: bad+=1
        await c.close()
    await b.close()
  print('QABAD',bad)
asyncio.run(m())
PEOF
mkdir -p /workspace/nox/agent/out; timeout 170 $PY /tmp/th_qa.py | tee /tmp/th_qa.out
if ! grep -q "QABAD 0" /tmp/th_qa.out; then
  echo ROLLBACK; for f in nox-theme.js nox-wow-bg.js nox-ds.js nox-actions.js; do [ -f $f.bak_th_$TS ] && cp $f.bak_th_$TS $f; done; rm -f nox-graphite.css nox-graphite-map.css
else echo QA_CLEAN; ls -la nox-graphite*.css; fi
echo done
