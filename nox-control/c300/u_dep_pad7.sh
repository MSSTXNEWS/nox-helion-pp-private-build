echo "C300: u_dep_pad7"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/u_pad/nox-u-pad.js -o /tmp/nox-u-pad.js || { echo FAIL; exit 0; }
node --check /tmp/nox-u-pad.js || { echo SYNTAX; exit 0; }
cp nox-u-pad.js nox-u-pad.js.bak_u7_$TS; cp /tmp/nox-u-pad.js nox-u-pad.js
sed -i 's#nox-u-pad.js?v=[a-z0-9]*#nox-u-pad.js?v=p7#' *.html
cat > /tmp/u_p7.py <<'PEOF'
import asyncio,json,urllib.request
from playwright.async_api import async_playwright
B='http://127.0.0.1:8091'
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();errs=[]
    c=await b.new_page();c.on('pageerror',lambda e:errs.append(str(e)[:90]))
    await c.goto(B+'/web/settings.html',wait_until='domcontentloaded');await c.wait_for_timeout(4000)
    await c.evaluate("NOXNote.open()");await c.fill('.up-p input:not(.up-q)','ПроектQA');await c.evaluate("NOXNote.add('U_QA_PAD7 текст',{to:'pad'})");await c.wait_for_timeout(4500)
    print('REMOTE',[n['text'][:40] for n in json.load(urllib.request.urlopen(B+'/api/notes'))['notes'] if n['id'].startswith('pad-')])
    c2=await b.new_page();await c2.goto(B+'/web/index.html',wait_until='domcontentloaded');await c2.evaluate("localStorage.removeItem('nox.pad.v1')");await c2.reload();await c2.wait_for_timeout(5000)
    await c2.evaluate("NOXNote.open()");await c2.wait_for_timeout(600)
    print('QA proj',await c2.evaluate("document.querySelector('.up-p input:not(.up-q)').value"),'text',await c2.evaluate("JSON.stringify(NOXNote.sheets()).slice(0,60)"),'ERRS',errs[:2])
    n=json.load(urllib.request.urlopen(B+'/api/notes'))['notes'];n=[x for x in n if 'U_QA_PAD' not in x['text']]
    urllib.request.urlopen(urllib.request.Request(B+'/api/notes',json.dumps({'notes':n}).encode(),{'Content-Type':'application/json'}))
    await b.close()
asyncio.run(m())
PEOF
timeout 90 $PY /tmp/u_p7.py 2>&1 | tee /tmp/u_p7.out | cut -c1-300
grep -q "ERRS \['" /tmp/u_p7.out && { cp nox-u-pad.js.bak_u7_$TS nox-u-pad.js; sed -i 's#nox-u-pad.js?v=p7#nox-u-pad.js?v=p6#' *.html; echo ROLLBACK; } || echo QA_CLEAN
