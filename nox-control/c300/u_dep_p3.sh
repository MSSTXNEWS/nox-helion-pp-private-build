echo "C300: u_dep_p3"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors "$R/u_p3/nox-u-p3.js?cb=$TS" -o /tmp/nox-u-p3.js || { echo FAIL; exit 0; }
node --check /tmp/nox-u-p3.js || { echo SYNTAX; exit 0; }
grep -q ubar /tmp/nox-u-p3.js || { echo STALE; exit 0; }
cp /tmp/nox-u-p3.js nox-u-p3.js
RG=/workspace/nox/web/pkg/server/svc_registry.json; cp $RG $RG.bak_up3_$TS
python3 - <<'PY'
import json
f='/workspace/nox/web/pkg/server/svc_registry.json';d=json.load(open(f))
if 'p3st' not in d: d['p3st']={"port":18230,"mode":"strip","title":"NOX P3 status"}
json.dump(d,open(f,'w'),ensure_ascii=False,indent=1);print('registry p3st',d['p3st'])
PY
cp system.html system.html.bak_up3_$TS
grep -q nox-u-p3.js system.html || sed -i 's#</body>#<script src="./nox-u-p3.js?v=p1" defer></script></body>#' system.html
sleep 2; for e in hunger train/status; do curl -s -m5 -o /dev/null -w "svc $e %{http_code}\n" http://127.0.0.1:8091/svc/p3st/$e; done
cat > /tmp/u_p3.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:90]))
      await c.goto('http://127.0.0.1:8091/web/system.html',wait_until='domcontentloaded');await c.wait_for_timeout(9000)
      print('QA',w,await c.evaluate("[!!document.getElementById('u-p3h'),document.querySelectorAll('#u-p3c canvas').length,document.querySelector('#u-p3h .tr')&&document.querySelector('#u-p3h .tr').textContent.slice(0,40),document.querySelector('#u-p3h .hv')&&document.querySelector('#u-p3h .hv').textContent,document.documentElement.scrollWidth<=innerWidth]"),'ERRS',[e for e in errs if 'percent' not in e][:2],flush=True)
      if w==1440: await c.screenshot(path='/workspace/nox/web/site/qa/u_p3.png')
      await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_p3.py | tee /tmp/u_p3.out
grep -q "ERRS \['" /tmp/u_p3.out && { cp system.html.bak_up3_$TS system.html; echo ROLLBACK; } || echo QA_CLEAN
