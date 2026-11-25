echo "C300: th_dep_gr5 (графики/граф/atlas/таблицы в серых тонах: JS-литералы цвета, Tabulator, Monaco)"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
SHA=__SHA__
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$SHA/nox-control/c300/bundles/th_graphite
G=/tmp/th_gr5; rm -rf $G; mkdir -p $G
for f in nox-graphite.css nox-theme.js patch.py th_gen_map.py; do curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/$f -o $G/$f && [ -s $G/$f ] || { echo "FAIL fetch $f"; exit 0; }; done
node --check $G/nox-theme.js || { echo FAIL_SYNTAX; exit 0; }
BK=/workspace/nox/web/th_gr5_bak_$TS; mkdir -p $BK; cp nox-*.js nox-graphite.css nox-graphite-map.css $BK/ 2>/dev/null; echo "$TS" > /workspace/nox/web/th_gr5.ts; ls $BK | wc -l
cat > /tmp/th_qa5.py <<'PEOF'
import asyncio,sys,json
from playwright.async_api import async_playwright
PAGES='index chat settings atlas training growth nexus memory organism assistant photo creative system music news cinema studio calendar finance'.split()
async def m(out):
  res={}
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
    for pg in PAGES:
      c=await b.new_page(viewport={'width':1440,'height':900});errs=[]
      c.on('pageerror',lambda e:errs.append(str(e)[:90]))
      try:
        await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=25000);await c.wait_for_timeout(3000)
        r=await c.evaluate("[document.documentElement.getAttribute('data-nox-theme'),window.NOXgx===true||window.NOXgx===undefined,window.NOXiconSet||'']")
        if out.endswith('after.json') and pg in ('index','chat','atlas','growth','nexus','organism','assistant'): await c.screenshot(path='/workspace/nox/agent/out/th5_%s_1440.jpg'%pg,type='jpeg',quality=70)
      except Exception as e: r=['EXC'];errs.append('EXC '+str(e)[:60])
      res[pg]={'e':sorted(set(errs)),'r':r};await c.close()
    await b.close()
  json.dump(res,open(out,'w'))
asyncio.run(m(sys.argv[1]))
PEOF
mkdir -p /workspace/nox/agent/out; timeout 200 $PY /tmp/th_qa5.py /tmp/th_qa5_before.json; echo baseline_done
cp $G/nox-graphite.css $G/nox-theme.js .
$PY $G/patch.py $S | grep -v "^already" | tr '\n' ';'; echo
$PY $G/th_gen_map.py $S $S/nox-graphite-map.css
timeout 200 $PY /tmp/th_qa5.py /tmp/th_qa5_after.json
$PY - <<'PEOF' > /tmp/th_qa5.cmp
import json
b=json.load(open('/tmp/th_qa5_before.json'));a=json.load(open('/tmp/th_qa5_after.json'));bad=0
for pg in a:
  new=[e for e in a[pg]['e'] if e not in b.get(pg,{}).get('e',[])]
  gr=a[pg]['r'][0]=='graphite'
  print('QA',pg,a[pg]['r'],'new_errs',new)
  if new or not gr: bad+=1
print('QABAD',bad)
PEOF
cat /tmp/th_qa5.cmp
if ! grep -q "QABAD 0" /tmp/th_qa5.cmp; then
  echo ROLLBACK; cp $BK/nox-*.js . ; cp $BK/nox-graphite.css $BK/nox-graphite-map.css . 2>/dev/null
else echo QA_CLEAN; fi
echo done
