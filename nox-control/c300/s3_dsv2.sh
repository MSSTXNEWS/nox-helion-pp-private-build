#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in v2.css v2.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3v2_$f || { echo FETCHFAIL $f; exit 1; }; done
cp $S/nox-ds.css $S/nox-ds.css.bak_s3_21; cp $S/nox-ds.js $S/nox-ds.js.bak_s3_21
grep -q "S3 ds-v2: состояния" $S/nox-ds.css || cat /tmp/s3v2_v2.css >> $S/nox-ds.css
grep -q "S3 ds-v2: aria-label" $S/nox-ds.js || cat /tmp/s3v2_v2.js >> $S/nox-ds.js
sed -i 's#nox-ds\.css?v=s3b#nox-ds.css?v=s3c#g; s#nox-ds\.js?v=s3b#nox-ds.js?v=s3c#g' $S/*.html $S/nox-dock-pop.js
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_v2.py <<'P'
from playwright.sync_api import sync_playwright
JS="""()=>{const bt=[...document.querySelectorAll('button,a[href],[role=button]')].filter(e=>e.getClientRects().length&&!e.closest('ninja-keys'));const noname=bt.filter(e=>!(e.textContent||'').trim()&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')&&!e.querySelector('img[alt]')).length;return {buttons:bt.length,noname,sel:(()=>{const s=document.querySelector('select');return s?getComputedStyle(s).backgroundImage.slice(0,20):null})(),tip:!!document.getElementById('ds-tip')}}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('index','music','chat','settings','system','cinema'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)[:100]))
        pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(5000)
        r=pg.evaluate(JS)
        pg.hover('#tbSearch'); pg.wait_for_timeout(400)
        tip=pg.evaluate("()=>{const t=document.getElementById('ds-tip');return t&&t.hasAttribute('data-on')?t.textContent:null}")
        print('R:',pgn,r,'tip:',tip,errs[:2]); ctx.close()
    b.close()
P
timeout 200 $PY -I /tmp/s3_v2.py 2>&1 | cut -c1-300
