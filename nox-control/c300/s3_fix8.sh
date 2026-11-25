#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
cp $S/nox-unify.css $S/nox-unify.css.bak_s3_8
grep -q "S3-HDR" $S/nox-unify.css || { echo; echo "/* S3-HDR: шапка одинакова на всех страницах, даже если страница не подключает nox-menu-x.css */"; grep -v "^/\*" $S/nox-menu-x.css; } >> $S/nox-unify.css
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_f8.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for n in ['cinema','music','news','studio','settings','index','chat']:
        pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/%s.html'%n,wait_until='load'); pg.wait_for_timeout(3000)
        print(n, pg.evaluate("()=>{const r=[...document.querySelectorAll('.tb-l > *')].filter(c=>getComputedStyle(c).display!='none').map(c=>Math.round(c.getBoundingClientRect().left));return {minLeft:Math.min(...r),n:r.length}}")); pg.close()
    b.close()
P
timeout 120 $PY -I /tmp/s3_f8.py 2>&1 | head
