PY=/workspace/nox/venv/bin/python
cat > /tmp/s3_sh12.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(4000)
    pg.click('#tbSearch'); pg.wait_for_timeout(1200)
    pg.keyboard.type('память',delay=60); pg.wait_for_timeout(4000)
    print('R:', pg.evaluate("()=>{const n=document.querySelector('ninja-keys');const t=n&&n.shadowRoot?n.shadowRoot.textContent.replace(/\\s+/g,' ').slice(0,500):'no ninja';return t}"))
    pg.screenshot(path='/tmp/g.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/g.png','-vf','scale=1000:-1','-q:v','8','/tmp/g.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/g.jpg','rb').read()).decode()); print('B64_END'); b.close()
P
timeout 120 $PY -I /tmp/s3_sh12.py 2>&1 | fold -w 900
