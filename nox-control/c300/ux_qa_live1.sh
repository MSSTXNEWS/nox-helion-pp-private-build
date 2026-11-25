echo "C300: ux_qa_live1"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
cat > /tmp/ql.py <<'PYX'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ['system','index','memory','knowledge','map','pdf','cinema','widgets','projects','atlas','board','qa','about','integrations']:
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
