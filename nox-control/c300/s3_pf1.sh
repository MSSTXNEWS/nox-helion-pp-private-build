#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in pf.css pf.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3pf_$f || { echo FETCHFAIL $f; exit 1; }; done
cp $S/nox-set-x.css $S/nox-set-x.css.bak_s3_26; cp $S/nox-set-x.js $S/nox-set-x.js.bak_s3_26; cp $S/nox-ds.js $S/nox-ds.js.bak_s3_26
grep -q "S3 pf: читаемая" $S/nox-set-x.css || cat /tmp/s3pf_pf.css >> $S/nox-set-x.css
sed -i "s/nc + ' с подтв.'/String(nc)/" $S/nox-set-x.js
grep -q "S3 pf: лупа" $S/nox-ds.js || cat /tmp/s3pf_pf.js >> $S/nox-ds.js
sed -i 's#nox-ds\.js?v=s3c#nox-ds.js?v=s3d#g' $S/*.html $S/nox-dock-pop.js
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_pf1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/news.html',wait_until='load'); pg.wait_for_timeout(3500)
    print('R: before', pg.evaluate("()=>document.getElementById('tbSearch').getAttribute('aria-expanded')"))
    pg.click('#tbSearch'); pg.wait_for_timeout(800); print('R: open', pg.evaluate("()=>[document.getElementById('tbSearch').getAttribute('aria-expanded'),document.documentElement.classList.contains('nox-palette-open')]"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(1200); print('R: closed', pg.evaluate("()=>document.getElementById('tbSearch').getAttribute('aria-expanded')"))
    b.close()
P
timeout 60 $PY -I /tmp/s3_pf1.py 2>&1 | cut -c1-200
