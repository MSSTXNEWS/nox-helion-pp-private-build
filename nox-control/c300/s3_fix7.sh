#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in patch_pl.py nox-worlds-prev.css menu-x-add.css nox-4k.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3f7_$f || { echo FETCHFAIL $f; exit 1; }; done
for f in nox-planets3d.js nox-menu-x.css nox-4k.css; do cp $S/$f $S/$f.bak_s3_7; done
$PY -I /tmp/s3f7_patch_pl.py || exit 1
cp /tmp/s3f7_nox-worlds-prev.css $S/nox-worlds-prev.css; cp /tmp/s3f7_nox-4k.css $S/nox-4k.css
grep -q "S3: шапка не обрезается" $S/nox-menu-x.css || cat /tmp/s3f7_menu-x-add.css >> $S/nox-menu-x.css
n=0; for f in $S/*.html; do grep -q 'nox-unify.css\|nox-shell.js' $f || continue
  grep -q 'nox-menu-x.css' $f || { sed -i 's#</head>#<link rel="stylesheet" href="./nox-menu-x.css">\n</head>#' $f; n=$((n+1)); }
  grep -q 'nox-4k.css' $f || sed -i 's#</head>#<link rel="stylesheet" href="./nox-4k.css">\n</head>#' $f
done; echo "menu-x linked into $n pages"
grep -q nox-worlds-prev.css $S/nox-worlds.js || sed -i '1i /* preview css */ (function(){var l=document.createElement("link");l.rel="stylesheet";l.href="./nox-worlds-prev.css";document.head.appendChild(l)})();' $S/nox-worlds.js
cp $S/nox-worlds.js /tmp/ok_w.js; 
$PY /workspace/nox/qa_ctl.py --pin
md5sum $S/nox-4k.css /tmp/s3f7_nox-4k.css | cut -c1-12
cat > /tmp/s3_f7.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
def b64(path,tag,w=900):
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',path,'-vf','scale=%d:-1'%w,'-q:v','16','/tmp/o_%s.jpg'%tag])
    print('B64_%s_BEGIN'%tag); print(base64.b64encode(open('/tmp/o_%s.jpg'%tag,'rb').read()).decode()); print('B64_%s_END'%tag)
with sync_playwright() as p:
    b=p.chromium.launch()
    for n in ['music','news','studio']:
        pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/%s.html'%n,wait_until='load'); pg.wait_for_timeout(3500)
        print(n, pg.evaluate("()=>{const r=[...document.querySelectorAll('.tb-l > *')].map(c=>Math.round(c.getBoundingClientRect().left));return {minLeft:Math.min(...r),n:r.length}}"))
        pg.screenshot(path='/tmp/h.png',clip={'x':0,'y':0,'width':1440,'height':70}); b64('/tmp/h.png','hd_'+n,1000); pg.close()
    errs=[]
    pg=b.new_page(viewport={'width':1440,'height':900}); pg.on('response',lambda r: errs.append(r.url) if r.status>=400 else None)
    pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(9000)
    print('404s', [e for e in errs if 'planet' in e])
    print('note', pg.evaluate("()=>{const n=document.querySelector('.nxpl-n');return n&&n.textContent}"))
    try:
        pg.evaluate("()=>{const e=document.querySelector('.nxpl');e&&e.scrollIntoView()}"); pg.wait_for_timeout(1500)
        pg.screenshot(path='/tmp/st.png'); b64('/tmp/st.png','set',1000)
    except Exception as e: print('shot err',e)
    pg.close()
    pg=b.new_page(viewport={'width':3840,'height':2160}); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(8000)
    print('4K', pg.evaluate("()=>{const z=parseFloat(getComputedStyle(document.documentElement).zoom);const c=[...document.querySelectorAll('#nxdock .nxd-cells a')].map(a=>a.getBoundingClientRect().right);const t=[...document.querySelectorAll('.tb a,.tb button')].map(a=>a.getBoundingClientRect().right);return {z,W:innerWidth/z,dockMaxRight:Math.max(...c)*1,tbMax:Math.max(...t)}}"))
    pg.screenshot(path='/tmp/k4.png'); b64('/tmp/k4.png','k4',900)
    b.close()
P
timeout 200 $PY -I /tmp/s3_f7.py 2>&1 | fold -w 900
