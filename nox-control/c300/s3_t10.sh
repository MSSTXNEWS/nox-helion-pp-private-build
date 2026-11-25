S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
post(){ curl -s -m 10 -X POST localhost:8091/api/cmd -H 'Content-Type: application/json' -d "$1" | head -c 300; echo; }
echo "== T10"; grep -c "String(a).trim" $S/nox-nav-x.js; grep -c nxsPersona $S/nox-settings-tabs.js; grep -c glance.html $S/nav.json; grep -c "persona.set" $S/qa/registry.json
post '{"name":"persona.set","params":{"curiosity":70,"humor":40,"strictness":55,"initiative":65,"empathy":80,"brevity":60}}'
post '{"name":"persona.set","params":{"humor":300}}'
post '{"name":"persona.get","params":{}}'
head -c 400 /workspace/nox/state/persona.json; echo
cat > /tmp/s3_t10.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)[:120]))
    pg.goto('http://localhost:8091/web/music.html',wait_until='load'); pg.wait_for_timeout(3000)
    print('crumb', pg.evaluate("()=>document.getElementById('nxx-crumb')&&document.getElementById('nxx-crumb').textContent"))
    pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(5000)
    pg.evaluate("()=>{const t=[...document.querySelectorAll('[data-tab],button,a')].find(e=>/Личность/.test(e.textContent)&&e.closest('nav,aside,.nxs-side,[role=tablist]')||false);t&&t.click()}"); pg.wait_for_timeout(2500)
    print('sliders', pg.evaluate("()=>document.querySelectorAll('#nxsPersona sl-range').length"), pg.evaluate("()=>(document.querySelector('.nxp-s')||{}).textContent"))
    pg.evaluate("()=>{const e=document.querySelector('#nxsPersona sl-range[data-k=humor]');if(e){e.value=85;e.dispatchEvent(new CustomEvent('sl-change',{bubbles:true}))}}"); pg.wait_for_timeout(2000)
    print('after', pg.evaluate("()=>(document.querySelector('.nxp-s')||{}).textContent"), errs[:3])
    pg.evaluate("()=>{const e=document.getElementById('nxsPersona');e&&e.scrollIntoView({block:'center'})}"); pg.wait_for_timeout(800)
    pg.screenshot(path='/tmp/p.png')
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/p.png','-vf','scale=1000:-1','-q:v','8','/tmp/p.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/p.jpg','rb').read()).decode()); print('B64_END')
    b.close()
P
timeout 150 $PY -I /tmp/s3_t10.py 2>&1 | fold -w 900
grep -o '"humor": *[0-9]*' /workspace/nox/state/persona.json
