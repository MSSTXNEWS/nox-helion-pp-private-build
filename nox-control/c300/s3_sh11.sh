PY=/workspace/nox/venv/bin/python
cat > /tmp/s3_sh11.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    pg.goto('http://localhost:8091/web/glance.html',wait_until='load'); pg.wait_for_timeout(9000)
    print('R:', pg.evaluate("()=>{const f=document.getElementById('glxf');return [f.style.display, document.getElementById('glxoff').style.display]}"))
    fr=[x for x in pg.frames if 'svc/glance' in x.url]; print('R: frame', len(fr), fr and fr[0].evaluate("document.body.innerText.slice(0,80)"))
    pg.screenshot(path='/tmp/g.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/g.png','-vf','scale=1000:-1','-q:v','8','/tmp/g.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/g.jpg','rb').read()).decode()); print('B64_END'); b.close()
P
timeout 120 $PY -I /tmp/s3_sh11.py 2>&1 | fold -w 900
