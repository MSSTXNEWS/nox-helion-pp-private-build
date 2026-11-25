#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== planets"; ls $S/vendor/planets/2k/ 2>&1 | head -40; ls $S/vendor/planets | head -20
echo "== grep nox-mercury"; grep -rn "nox-mercury\|nox-\${\|nox-'" $S/nox-planets3d.js | head
echo "== zoom sources"; grep -ln "zoom:" $S/*.css | head -20; grep -n "zoom" $S/nox-4k.css $S/nox-vt.css | head
echo "== link 4k in index"; grep -n "nox-4k" $S/index.html | head -3
echo "== head diff"; for p in cinema music news studio; do echo -- $p; grep -o '<link[^>]*stylesheet[^>]*>' $S/$p.html | sed 's/.*href="\([^"]*\)".*/\1/' | tr '\n' ' '; echo; grep -c "<style" $S/$p.html; done
cat > /tmp/s3_d1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg_ in ['cinema','music','news','studio','settings']:
        pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/%s.html'%pg_,wait_until='load'); pg.wait_for_timeout(3500)
        print(pg_, pg.evaluate("""()=>{const t=document.querySelector('.tb');const cs=getComputedStyle(t);const k=[...t.children].map(c=>{const r=c.getBoundingClientRect();return c.className.toString().slice(0,18)+':'+Math.round(r.left)+'-'+Math.round(r.right)});return {disp:cs.display,jc:cs.justifyContent,pos:cs.position,ml:cs.marginLeft,w:Math.round(t.getBoundingClientRect().width),left:Math.round(t.getBoundingClientRect().left),ov:cs.overflow,zoom:getComputedStyle(document.documentElement).zoom,bodyz:getComputedStyle(document.body).zoom,k:k.slice(0,14)}}"""))
        pg.close()
    b.close()
P
$PY -I /tmp/s3_d1.py 2>&1 | head -40
