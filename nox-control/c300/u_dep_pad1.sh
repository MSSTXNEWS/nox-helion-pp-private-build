echo "C300: u_dep_pad1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/u_pad/nox-u-pad.js -o /tmp/nox-u-pad.js || { echo FAIL; exit 0; }
node --check /tmp/nox-u-pad.js || { echo SYNTAX; exit 0; }
[ -s nox-u-pad.js ] && cp nox-u-pad.js nox-u-pad.js.bak_u_$TS
cp /tmp/nox-u-pad.js nox-u-pad.js
mkdir -p /tmp/padbak_$TS; INJ=""
for f in *.html; do case $f in *reader*|*library*|*book*) continue;; esac
 grep -q "nox-u-pad.js" $f && { sed -i 's#nox-u-pad.js?v=[a-z0-9]*#nox-u-pad.js?v=p1#' $f; continue; }
 grep -q "</body>" $f || continue
 cp $f /tmp/padbak_$TS/$f; sed -i 's#</body>#<script src="./nox-u-pad.js?v=p1" defer></script></body>#' $f; INJ="$INJ $f"
done
echo "injected:$INJ" | cut -c1-300
cat > /tmp/u_pad.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg,w,h in(('index',1440,900),('creative',1440,900),('settings',1440,900),('index',390,844)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg+('?home=1' if w<500 else ''),wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      r=await c.evaluate("[!!document.getElementById('u-pad'),!!document.getElementById('u-tab'),typeof NOXNote]")
      if w>500:
        await c.keyboard.press('n');await c.wait_for_timeout(700);await c.keyboard.type('qa pad');await c.wait_for_timeout(500)
        r.append(await c.evaluate("[document.getElementById('u-pad').className,!!document.querySelector('#u-pad .CodeMirror'),(localStorage.getItem('nox.pad.v1')||'').includes('qa pad')]"))
        await c.screenshot(path='/workspace/nox/web/site/qa/u_pad_%s.png'%pg)
      print('QA',pg,w,r,'ERRS',errs[:2],flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 120 $PY /tmp/u_pad.py | tee /tmp/u_pad.out
grep -E "^QA" /tmp/u_pad.out | grep -q "ERRS \['" && { for f in $INJ; do cp /tmp/padbak_$TS/$f $f; done; echo ROLLBACK; } || echo QA_CLEAN
echo done
