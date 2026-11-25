echo "C300: ux_dep_p4"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/cdf499430418023b72507caa6100769c56c0c916/nox-control/c300/bundles/ux_p4
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $RAW/nox-ux-fab.js -o /tmp/nox-ux-fab.js && node --check /tmp/nox-ux-fab.js && curl -fsSL --retry 5 $RAW/patch.py -o /tmp/ux_p4_patch.py || { echo FAIL_FETCH; exit 0; }
cp /tmp/nox-ux-fab.js nox-ux-fab.js
python3 /tmp/ux_p4_patch.py ux$TS; node --check nox-k4-core.js && echo OK_k4 || { cp nox-k4-core.js.bak_ux_ux$TS nox-k4-core.js; echo ROLLBACK; }
cat > /tmp/ux_p4_qa.py <<'PYX'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ['system','index','memory','knowledge','map','pdf','cinema','widgets']:
        for w in (1440,390):
            c=b.new_context(viewport={'width':w,'height':850});g=c.new_page();er=[]
            g.on('pageerror',lambda e:er.append(str(e)[:100]))
            try:
                g.goto('http://127.0.0.1:8091/'+pg+('.html?home=1' if pg=='index' else '.html'),wait_until='load',timeout=25000);g.wait_for_timeout(3000)
                d=g.evaluate("()=>({hs:document.documentElement.scrollWidth-innerWidth,fab:!!document.querySelector('#ux-fab'),items:document.querySelectorAll('#ux-fab sl-menu-item').length,old:getComputedStyle(document.getElementById('k4-fab')||document.body).display})")
            except Exception as e: d='ERR '+str(e)[:50]
            print('QA',pg,w,d,'EXC' if er else 'ok',er[:2]);c.close()
    b.close()
PYX
timeout 150 /workspace/nox/venv/bin/python /tmp/ux_p4_qa.py | tee /tmp/ux_p4_qa.out
grep -E "^QA.*EXC" /tmp/ux_p4_qa.out && { cp nox-k4-core.js.bak_ux_ux$TS nox-k4-core.js; rm -f nox-ux-fab.js; echo ROLLBACK_ALL; } || echo QA_CLEAN
