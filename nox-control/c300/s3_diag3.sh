#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== refs"; grep -ln "nox-mercury\|nox-venus\|nox-earth" $S/*.js $S/*.html $S/*.css 2>/dev/null
grep -n "nox-'\|nox-\"\|nox-\`\|2k_\|\.jpg" $S/nox-planets3d.js | head -20
grep -o "[a-z-]*mercury[^'\" )]*" $S/nox-settings-tabs.js $S/settings.html 2>/dev/null | sort | uniq | head
cat > /tmp/s3_d2.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for n in ['cinema','music']:
        pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/%s.html'%n,wait_until='load'); pg.wait_for_timeout(3500)
        print(n, pg.evaluate("""()=>{return [...document.querySelectorAll('.tb-l > *, .tb-r > *')].map(c=>{const r=c.getBoundingClientRect(),s=getComputedStyle(c);return (c.id||c.className.toString()||c.tagName).slice(0,16)+' '+Math.round(r.left)+'-'+Math.round(r.right)+' w'+Math.round(r.width)+' fs'+s.fontSize+' pad'+s.padding+' ov'+s.overflow+' tr'+s.transform.slice(0,24)}).join(' | ')}"""))
        pg.screenshot(path='/tmp/h.png',clip={'x':0,'y':0,'width':1440,'height':70})
        subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/h.png','-q:v','12','/tmp/h_%s.jpg'%n])
        print('B64_%s_BEGIN'%n); print(base64.b64encode(open('/tmp/h_%s.jpg'%n,'rb').read()).decode()); print('B64_%s_END'%n)
        pg.close()
    b.close()
P
timeout 150 $PY -I /tmp/s3_d2.py 2>&1 | fold -w 900 | head -60
