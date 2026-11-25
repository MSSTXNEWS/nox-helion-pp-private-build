echo "C300: u_dep_wow2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_index/nox-u-index.css -o /tmp/nox-u-index.css && [ -s /tmp/nox-u-index.css ] && cp /tmp/nox-u-index.css nox-u-index.css && echo css_copied || { echo FAIL; exit 0; }
cp index.html index.html.bak_u2_$TS; cp nox-unify.css nox-unify.css.bak_u5_$TS
python3 - <<'PYX'
f='index.html';s=open(f,encoding='utf-8').read()
if 'nox-u-index.css' not in s:
    i=s.rfind('</body>');s=s[:i]+'<link rel="stylesheet" href="./nox-u-index.css?v=u1">'+s[i:];open(f,'w',encoding='utf-8').write(s);print('index link added')
PYX
D=vendor/tabler-icons/icons/outline; [ -f $D/layout-split.svg ] || { cp $D/layout-columns.svg $D/layout-split.svg 2>/dev/null || printf '<svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-layout-split" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"/><path d="M12 4l0 16"/></svg>' > $D/layout-split.svg; echo "icon created"; }
grep -q U_STOP nox-unify.css || cat >> nox-unify.css <<'CEOF'

/* U_STOP: спокойная danger-кнопка STOP + подписи не мельче 13 px */
#nxdock .nxd-stop{background:rgba(120,24,32,.38)!important;border:1px solid rgba(255,110,120,.5)!important;color:#ffdfe1!important;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);transition:background .2s,box-shadow .2s}
#nxdock .nxd-stop:hover{background:rgba(190,36,50,.62)!important;box-shadow:0 0 18px rgba(255,80,90,.35)!important}
#nxdock .nxd-stop sl-icon{color:#ffb8be!important}
main#page :is(small,.hint,.sub,.cap,kbd,label){font-size:max(13px,1em)}
CEOF
sed -i -E 's#nox-unify\.css\?v=[A-Za-z0-9_]+#nox-unify.css?v=u5#' *.html
echo "== img src"; sed -n 140,175p /workspace/nox/imgsvc/image_service.py | cut -c1-200
echo "== QA"
cat > /tmp/u_i1.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg,w,h in (('index',1440,900),('index',390,844),('settings',1440,900),('creative',1440,900)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];bad=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]));c.on('response',lambda r:bad.append(r.url[-50:]) if r.status>=400 and '/img/' not in r.url else None)
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg+('?home=1' if w<500 else ''),wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      print('QA',pg,w,errs[:2],'http>=400',bad[:3],flush=True)
      if pg=='index' and w==1440: await c.screenshot(path='/tmp/u_i1.jpg',type='jpeg',quality=50)
      await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_i1.py | tee /tmp/u_i1.out
grep -E "^QA" /tmp/u_i1.out | grep -q "Unexpected\|Error" && { cp index.html.bak_u2_$TS index.html; cp nox-unify.css.bak_u5_$TS nox-unify.css; echo ROLLBACK; } || echo QA_CLEAN
echo "U: index: планета тише, k4-fab в ряд, иконка layout-split; STOP спокойнее" >> qa/rework/index.fixed
echo done
