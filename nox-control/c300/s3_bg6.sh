#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/bg6.css?v=$(date +%s)" -o /tmp/s3bg6.css || exit 1
cp $S/nox-ds.css $S/nox-ds.css.bak_s3_20
grep -q "запас на браузеры без blur по WebGL-фону" $S/nox-ds.css || cat /tmp/s3bg6.css >> $S/nox-ds.css
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_bg6.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/system.html',wait_until='load'); pg.wait_for_timeout(5000)
    pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END'); b.close()
P
timeout 90 $PY -I /tmp/s3_bg6.py 2>&1 | fold -w 900
