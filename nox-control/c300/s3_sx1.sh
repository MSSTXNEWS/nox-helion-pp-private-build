#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox-set-x.js nox-set-x.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3sx_$f || { echo FETCHFAIL $f; exit 1; }; done
cp /tmp/s3sx_nox-set-x.js $S/nox-set-x.js; cp /tmp/s3sx_nox-set-x.css $S/nox-set-x.css; cp $S/settings.html $S/settings.html.bak_s3_25
grep -q nox-set-x.js $S/settings.html || sed -i 's#</head>#<link rel="stylesheet" href="./nox-set-x.css">\n<script src="./nox-set-x.js" defer></script>\n</head>#' $S/settings.html
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_sx1.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)[:120]))
    pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(6000)
    print('R: badges', pg.evaluate("()=>[...document.querySelectorAll('sl-badge.nxm-st')].map(b=>b.closest('[role=tab]').dataset.tab+':'+b.textContent+'/'+b.variant)"))
    pg.evaluate("()=>[...document.querySelectorAll('.nxm-side [role=tab]')].find(b=>/Модели/.test(b.textContent)).click()"); pg.wait_for_timeout(1500)
    print('R: depth', pg.evaluate("()=>{const g=document.getElementById('nxsDepth2');return g?g.value:'no sl-radio-group'}"))
    pg.evaluate("()=>{const g=document.getElementById('nxsDepth2');if(g){g.value='deep';g.dispatchEvent(new CustomEvent('sl-change',{bubbles:true}))}}"); pg.wait_for_timeout(300)
    print('R: stored', pg.evaluate("()=>localStorage.getItem('nox.depth')"), 'errs', errs[:3])
    pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END'); b.close()
P
timeout 100 $PY -I /tmp/s3_sx1.py 2>&1 | fold -w 900
