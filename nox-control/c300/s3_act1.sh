#!/bin/bash
S=/workspace/nox/web/site; T=bak_s3_4
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
cd $S
[ -f nox-ninja.js.$T ] || cp nox-ninja.js nox-ninja.js.$T
for f in nox-actions.js nox-cast-btn.js nox-vt.css nox-ninja.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3a_$f && cp /tmp/s3a_$f $S/$f && echo placed $f; done
n=0
for f in $S/*.html; do
  grep -q "nox-pult.js" $f || continue
  grep -q 'nox-vt.css' $f || { sed -i 's#</head>#<link rel="stylesheet" href="./nox-vt.css">\n</head>#' $f; n=$((n+1)); }
  grep -q 'nox-actions.js' $f || sed -i 's#</body>#<script src="./nox-actions.js" defer></script><script src="./nox-cast-btn.js" defer></script>\n</body>#' $f
done
echo "injected $n"
ls vendor/planets 2>&1 | head -12
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_act_shot.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s3a_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','14',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
B='http://localhost:8091/web/'
with sync_playwright() as p:
    b=p.chromium.launch()
    c=b.new_context(viewport={'width':1440,'height':900}); pg=c.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
    pg.goto(B+'index.html',wait_until='load'); pg.wait_for_timeout(3500)
    pg.click('#tbSearch'); pg.wait_for_timeout(700); pg.keyboard.type('проектор',delay=40); pg.wait_for_timeout(900)
    pg.screenshot(path='/tmp/s.png'); out('search_d','/tmp/s.png',900); print('ERRS',errs[:3])
    pg.keyboard.press('Escape'); pg.click('#nxsun'); pg.wait_for_timeout(600); pg.screenshot(path='/tmp/s.png'); out('pult_d','/tmp/s.png',900)
    print('ACT',pg.evaluate("[window.NOXactions&&NOXactions.list.length,!!document.querySelector('[data-act=cast]')]"))
    c2=b.new_context(viewport={'width':3840,'height':2160}); p2=c2.new_page(); p2.goto(B+'index.html',wait_until='load'); p2.wait_for_timeout(4000)
    print('4K over',p2.evaluate("document.documentElement.scrollWidth-innerWidth")); p2.screenshot(path='/tmp/s.png'); out('k4','/tmp/s.png',900)
    c3=b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True); p3=c3.new_page(); p3.goto(B+'index.html',wait_until='load'); p3.wait_for_timeout(3000)
    p3.click('#nxsun'); p3.wait_for_timeout(600); p3.screenshot(path='/tmp/s.png'); out('pult_m','/tmp/s.png',390)
    b.close()
P
/workspace/nox/venv/bin/python -I /tmp/s3_act_shot.py 2>&1 | cut -c1-900
