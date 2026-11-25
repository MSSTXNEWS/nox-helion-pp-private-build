#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
cp $S/nox-4k.css $S/nox-4k.css.bak_s3_7
curl -fsSL "$RAW/nox-4k.css?v=$(date +%s)" -o /tmp/s3k4.css || exit 1
cp /tmp/s3k4.css $S/nox-4k.css
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_4k3.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':3840,'height':2160}); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(9000)
    print('4K', pg.evaluate("""()=>{const z=parseFloat(getComputedStyle(document.documentElement).zoom);const W=innerWidth/z;const r=e=>{const q=document.querySelector(e);if(!q)return null;const b=q.getBoundingClientRect();return [Math.round(b.left),Math.round(b.right)]};
    const cells=[...document.querySelectorAll('#nxdock .nxd-cells a')].map(a=>a.getBoundingClientRect());const tb=[...document.querySelectorAll('.tb a,.tb button')].map(a=>a.getBoundingClientRect().right);
    return {z,W,dockMaxRight:Math.round(Math.max(...cells.map(c=>c.right))),tbMaxRight:Math.round(Math.max(...tb)),dock:r('#nxdock'),tb:r('.tb')}}"""))
    pg.screenshot(path='/tmp/s.png')
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=900:-1','-q:v','15','/tmp/s3_k4.jpg'])
    print('B64_k4_BEGIN'); print(base64.b64encode(open('/tmp/s3_k4.jpg','rb').read()).decode()); print('B64_k4_END')
    b.close()
P
$PY -I /tmp/s3_4k3.py 2>&1 | fold -w 900
