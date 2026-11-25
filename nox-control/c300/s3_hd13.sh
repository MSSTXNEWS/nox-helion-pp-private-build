#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/hd-add.css?v=$(date +%s)" -o /tmp/s3hd.css || exit 1
cp $S/nox-unify.css $S/nox-unify.css.bak_s3_11
grep -q "S3-HDR2" $S/nox-unify.css || cat /tmp/s3hd.css >> $S/nox-unify.css
V=$(date +%s); for f in $S/*.html; do grep -q 'nox-unify.css' $f || continue; sed -i -E "s#nox-unify\.css(\?v=[A-Za-z0-9]*)?\"#nox-unify.css?v=s3_$V\"#; s#nox-menu-x\.css(\?v=[A-Za-z0-9_]*)?\"#nox-menu-x.css?v=s3_$V\"#; s#nox-nav-x\.js(\?v=[A-Za-z0-9_]*)?\"#nox-nav-x.js?v=s3_$V\"#" $f; done
cp $S/sw.js $S/sw.js.bak_s3_11; sed -i "s/const V = 'nox-s1-v3'/const V = 'nox-s1-v3-s3b'/" $S/sw.js
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_hd13.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('music','cinema','settings'):
      for w in (1200,1280,1366,1440,1536,1600,1700,1920):
        ctx=b.new_context(viewport={'width':w,'height':900},service_workers='block'); pg=ctx.new_page()
        pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(2200)
        print('W',pgn,w, pg.evaluate("()=>{const L=[...document.querySelectorAll('.tb-l > *')].filter(c=>getComputedStyle(c).display!='none');const R=[...document.querySelectorAll('.tb-r > *')].filter(c=>getComputedStyle(c).display!='none');const t=document.querySelector('.tb-l'),u=document.querySelector('.tb-r');return [Math.round(Math.min(...L.map(c=>c.getBoundingClientRect().left))),Math.round(Math.max(...R.map(c=>c.getBoundingClientRect().right))),innerWidth,t.scrollLeft,t.scrollWidth-t.clientWidth,u.scrollWidth-u.clientWidth]}"))
        ctx.close()
    b.close()
P
timeout 200 $PY -I /tmp/s3_hd13.py 2>&1 | cut -c1-200
