#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== D8"; grep -c "nox-menu-x.css" $S/studio.html; grep -o '<link[^>]*stylesheet[^>]*>' $S/studio.html | sed 's/.*href="\([^"]*\)".*/\1/' | tr '\n' ' '; echo
grep -n "tb-t\|tb-i" $S/studio.html | cut -c1-200 | head -5
cat > /tmp/s3_d8.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/studio.html',wait_until='load'); pg.wait_for_timeout(4000)
    print(pg.evaluate("()=>[...document.querySelectorAll('.tb-l > *')].map(c=>(c.className+'|'+(c.dataset.k||'')+'|'+getComputedStyle(c).display+'|'+Math.round(c.getBoundingClientRect().left)+'-'+Math.round(c.getBoundingClientRect().right)).slice(0,60)).join('\\n')"))
    print(pg.evaluate("()=>[getComputedStyle(document.querySelector('.tb-l')).cssText.length, getComputedStyle(document.querySelector('.tb-l')).width, document.querySelector('.tb-l').parentElement.className]"))
    b.close()
P
timeout 100 $PY -I /tmp/s3_d8.py 2>&1 | head -30
