echo "C300: ui_dep1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/ui_ux/nox-u-ux.css -o /tmp/nox-u-ux.css && curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/ui_ux/nox-u-ux.js -o /tmp/nox-u-ux.js && node --check /tmp/nox-u-ux.js && [ -s /tmp/nox-u-ux.css ] || { echo FAIL; exit 0; }
PAGES="index creative settings"
mkdir -p /tmp/uibak_$TS; for f in nox-u-ux.css nox-u-ux.js; do [ -f $f ] && cp $f /tmp/uibak_$TS/$f; done
cp /tmp/nox-u-ux.css nox-u-ux.css; cp /tmp/nox-u-ux.js nox-u-ux.js
python3 - $PAGES <<'P'
import sys,re
for p in sys.argv[1:]:
    f=p+'.html'; s=open(f,encoding='utf-8').read()
    open('/tmp/uibak_%s_%s.html'%(sys.argv[0] and 'x',p),'w',encoding='utf-8').write(s)
    if 'nox-u-ux.css' not in s:
        i=s.rfind('</body>'); s=s[:i]+'<link rel="stylesheet" href="./nox-u-ux.css?v=x1"><script src="./nox-u-ux.js?v=x1" defer></script>'+s[i:]
    else: s=re.sub(r'nox-u-ux\.(css|js)\?v=\w+',lambda m:'nox-u-ux.%s?v=x1'%m.group(1),s)
    open(f,'w',encoding='utf-8').write(s); print('ok',f)
P
cat > /tmp/ui_qa.py <<'PEOF'
import asyncio,json
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('index.html?home=1','creative.html','settings.html'):
      for w,h in((1440,900),(390,844)):
        c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
        await c.goto('http://127.0.0.1:8091/web/'+pg,wait_until='domcontentloaded');await c.wait_for_timeout(5500)
        r=await c.evaluate("""()=>{const o=[];for(const e of document.querySelectorAll('.tb-t,.tb-i,#nxdock a,#nxdock button')){const r=e.getBoundingClientRect();if(r.width&&r.height&&(r.height<43.5))o.push((e.id||e.className).toString().slice(0,20)+':'+Math.round(r.height))}return [o.length,o.slice(0,3),document.documentElement.scrollWidth<=innerWidth]}""")
        print('QA',pg,w,errs[:2],r,flush=True)
        if w==1440: await c.screenshot(path='/workspace/nox/agent/out/ui_dep1_%s.jpg'%pg.split('.')[0],type='jpeg',quality=80)
        await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 120 $PY /tmp/ui_qa.py | tee /tmp/ui_qa.out
if grep -E "^QA" /tmp/ui_qa.out | grep -q "\['"; then for p in $PAGES; do cp /tmp/uibak_x_$p.html $p.html; done; echo ROLLBACK; else echo QA_CLEAN; fi
D=/workspace/nox/state/mock_qa; mkdir -p $D; LIST="a1_index_1440.jpg a1_creative_1440.jpg a1_settings_1440.jpg"
for f in $LIST; do curl -fsSL --retry 3 $R/ui_crit/$f -o $D/$f || echo MISS $f; done
curl -fsSL $R/ui_crit/crit.py -o /tmp/ui_crit.py; rm -f /workspace/nox/agent/out/ui_d1_prog.txt
setsid -f nohup python3 /tmp/ui_crit.py d1 $LIST >/workspace/nox/agent/out/ui_d1.log 2>&1 </dev/null
echo started
