echo "C300: ui_dep6"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ui_ux
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/nox-u-ux.css -o /tmp/nox-u-ux.css && curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/nox-u-ux.js -o /tmp/nox-u-ux.js && node --check /tmp/nox-u-ux.js && [ -s /tmp/nox-u-ux.css ] || { echo FAIL; exit 0; }
PAGES=""; for p in tools studio photo voice training dispatcher downloads assistant board atlas pdf integrations; do [ -f $p.html ] && PAGES="$PAGES $p"; done; echo PAGES $PAGES
mkdir -p /tmp/uibak6_$TS; cp nox-u-ux.css nox-u-ux.js /tmp/uibak6_$TS/; for p in $PAGES; do cp $p.html /tmp/uibak6_$TS/$p.html; done
cp /tmp/nox-u-ux.css nox-u-ux.css; cp /tmp/nox-u-ux.js nox-u-ux.js
python3 - $PAGES <<'P'
import sys,re
for p in sys.argv[1:]:
    f=p+'.html'; s=open(f,encoding='utf-8').read()
    if 'nox-u-ux.css' not in s:
        i=s.rfind('</body>'); s=s[:i]+'<link rel="stylesheet" href="./nox-u-ux.css?v=x5"><script src="./nox-u-ux.js?v=x5" defer></script>'+s[i:]
    else: s=re.sub(r'nox-u-ux\.(css|js)\?v=\w+',lambda m:'nox-u-ux.%s?v=x5'%m.group(1),s)
    open(f,'w',encoding='utf-8').write(s)
P
cat > /tmp/ui_qa6.py <<'PEOF'
import asyncio,sys
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in sys.argv[1:]:
      for w,h in((1440,900),(390,844)):
        c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
        await c.goto('http://127.0.0.1:8091/web/'+pg+('.html?home=1' if pg=='index' else '.html'),wait_until='domcontentloaded');await c.wait_for_timeout(5000)
        r=await c.evaluate("""()=>{const o=[];for(const e of document.querySelectorAll('.tb-t,.tb-i,#nxdock a,#nxdock button')){const r=e.getBoundingClientRect();if(r.width&&r.height&&r.height<43.5)o.push((e.id||e.className).toString().slice(0,20)+':'+Math.round(r.height))}return [o.length,document.documentElement.scrollWidth<=innerWidth,document.querySelectorAll('.ds-empty').length,document.querySelectorAll('.u-skel').length]}""")
        if pg=='creative' and w==1440:
          r.append(await c.evaluate("(()=>{try{const cv=NOXDZ.cv;const a=cv.getObjects().filter(o=>o.dzArt)[0];const el=cv.getElement().getBoundingClientRect();const par=cv.getElement().closest('#dzStage,.canvas-container')||cv.getElement().parentElement;const pr=par.parentElement.getBoundingClientRect();return {zoom:cv.getZoom(),cv:[cv.getWidth(),cv.getHeight()],el:[Math.round(el.x),Math.round(el.y),Math.round(el.width),Math.round(el.height)],stage:[Math.round(pr.x),Math.round(pr.y),Math.round(pr.width),Math.round(pr.height)],art:a&&[a.left,a.top,a.width,a.height],vpt:cv.viewportTransform}}catch(e){return String(e)}})()"))
        print('QA',pg,w,errs[:2],r,flush=True); await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 300 $PY /tmp/ui_qa6.py $PAGES | tee /tmp/ui_qa6.out
if grep -E "^QA" /tmp/ui_qa6.out | grep -E "QA [a-z]+ [0-9]+ \['"; then for p in $PAGES; do cp /tmp/uibak6_$TS/$p.html $p.html; done; echo ROLLBACK; else echo QA_CLEAN; fi
echo "== cta"; $PY - $PAGES <<'P'
import asyncio,sys
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in sys.argv[1:]:
      c=await b.new_page(viewport={'width':1440,'height':900});await c.goto('http://127.0.0.1:8091/web/'+pg+'.html',wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      print('CTA',pg,await c.evaluate("[...document.querySelectorAll('.u-cta')].map(e=>(e.textContent||'').trim().slice(0,20))"),flush=True);await c.close()
    await b.close()
asyncio.run(m())
P
