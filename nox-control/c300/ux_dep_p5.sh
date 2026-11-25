echo "C300: ux_dep_p5"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
S=/workspace/nox/web/site; cd $S; TS=$(date +%s); export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/6604bff61b3c935320147dc1997487dbb75ac5bc/nox-control/c300/bundles/ux_p5/patch.py -o /tmp/ux_p5_patch.py || { echo FAIL_FETCH; exit 0; }
python3 /tmp/ux_p5_patch.py ux$TS; node --check nox-dock-pop.js && echo OK_dp || { cp nox-dock-pop.js.bak_ux_ux$TS nox-dock-pop.js; echo ROLLBACK; }
cat > /tmp/ql.py <<'PYX'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ['map','widgets','projects','board','qa','about','integrations','mail','music']:
        for w in (1440,390):
            c=b.new_context(viewport={'width':w,'height':850});g=c.new_page();er=[];bd=[]
            g.on('pageerror',lambda e:er.append(str(e)[:90]))
            g.on('response',lambda r:bd.append(str(r.status)+' '+r.url[-50:]) if r.status>=400 and not any(x in r.url for x in('/api','/v7','/glm','/brain','/memory/','/cal','/stt','/tts')) else None)
            try:
                g.goto('http://127.0.0.1:8091/web/'+pg+('.html?home=1' if pg=='index' else '.html'),wait_until='load',timeout=30000);g.wait_for_timeout(5000)
                d=g.evaluate("()=>({t:document.title.slice(0,25),hs:document.documentElement.scrollWidth-innerWidth,fab:!!document.querySelector('#ux-fab'),items:document.querySelectorAll('#ux-fab sl-menu-item').length,oldvis:(()=>{const e=document.getElementById('k4-fab');return e?getComputedStyle(e).display:'none'})(),stop:(()=>{const e=document.getElementById('dkStop');return e?getComputedStyle(e).display:'-'})()})")
            except Exception as e: d='ERR '+str(e)[:50]
            print('QL',pg,w,d,'EXC' if er else 'ok',er[:2],bd[:3]);c.close()
    b.close()
PYX
timeout 170 /workspace/nox/venv/bin/python /tmp/ql.py 2>&1 | grep "^QL"
