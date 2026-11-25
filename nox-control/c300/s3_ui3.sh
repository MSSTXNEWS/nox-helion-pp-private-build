#!/bin/bash
S=/workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox-radial.js nox-vt.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3u3_$f && cp /tmp/s3u3_$f $S/$f && echo placed $f; done
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_u3.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s3_u3_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','16',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
B='http://localhost:8091/web/'
with sync_playwright() as p:
    b=p.chromium.launch()
    c=b.new_context(viewport={'width':1440,'height':900}); pg=c.new_page(); pg.goto(B+'index.html',wait_until='load'); pg.wait_for_timeout(3500)
    r=pg.evaluate("(()=>{const r=document.getElementById('nxsun').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()")
    pg.mouse.move(r[0],r[1]); pg.mouse.down(); pg.wait_for_timeout(1000); pg.screenshot(path='/tmp/s.png'); out('radial',  '/tmp/s.png',620); pg.mouse.up()
    c2=b.new_context(viewport={'width':3840,'height':2160}); p2=c2.new_page(); p2.goto(B+'index.html',wait_until='load'); p2.wait_for_timeout(5000)
    print('4K over',p2.evaluate("[document.documentElement.scrollWidth-innerWidth,innerWidth]")); p2.screenshot(path='/tmp/s.png'); out('k4','/tmp/s.png',620)
    b.close()
P
/workspace/nox/venv/bin/python -I /tmp/s3_u3.py 2>&1 | cut -c1-900
