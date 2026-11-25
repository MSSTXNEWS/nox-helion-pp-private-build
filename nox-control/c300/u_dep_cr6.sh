echo "C300: u_dep_cr6"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_creative/nox-u-creative.js -o /tmp/nox-u-creative.js && node --check /tmp/nox-u-creative.js && cp nox-u-creative.js nox-u-creative.js.bak_u4_$TS && cp /tmp/nox-u-creative.js nox-u-creative.js && echo copied || { echo FAIL; exit 0; }
sed -i 's#nox-u-creative.js?v=u[0-9]#nox-u-creative.js?v=u4#' creative.html
cat > /tmp/u_cr8.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/creative.html',wait_until='domcontentloaded');await c.wait_for_timeout(6000)
      r=await c.evaluate("[!!document.getElementById('u-hkb'),document.querySelectorAll('#k8-chat .k4-btn.pri').length,Math.round(NOXDZ.cv.getZoom()*100)]")
      if w==1440:
        await c.click('#u-hkb');await c.wait_for_timeout(700);r.append(await c.evaluate("!!document.querySelector('#u-hk[open]')"))
        await c.keyboard.press('Escape')
      print('QA',w,r,errs[:2],flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 80 $PY /tmp/u_cr8.py | tee /tmp/u_cr8.out
grep -E "^QA" /tmp/u_cr8.out | grep -q "\['\|Unexpected\|Error\|EXC" && { cp nox-u-creative.js.bak_u4_$TS nox-u-creative.js; sed -i 's#nox-u-creative.js?v=u4#nox-u-creative.js?v=u1#' creative.html; echo ROLLBACK; } || echo QA_CLEAN
echo "== index css v2"
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_index/nox-u-index.css -o /tmp/nox-u-index.css && [ -s /tmp/nox-u-index.css ] && cp nox-u-index.css nox-u-index.css.bak_u4_$TS && cp /tmp/nox-u-index.css nox-u-index.css && sed -i "s#nox-u-index.css?v=u[0-9]#nox-u-index.css?v=u2#" index.html && echo index_css_updated
cat > /tmp/u_ix.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h,u in((1440,900,'index.html'),(390,844,'index.html?home=1')):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/'+u,wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      print('QAI',w,errs[:2],await c.evaluate("document.documentElement.scrollWidth<=innerWidth"),flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 60 $PY /tmp/u_ix.py | tee /tmp/u_ix.out
grep -E "^QAI" /tmp/u_ix.out | grep -q "\['" && { cp nox-u-index.css.bak_u4_$TS nox-u-index.css; echo ROLLBACK_INDEX; } || echo INDEX_CLEAN
echo "== audit"; cat /workspace/nox/agent/out/u_qab_prog.txt | cut -c1-300; pgrep -af qa_audit | cut -c1-80
echo done
