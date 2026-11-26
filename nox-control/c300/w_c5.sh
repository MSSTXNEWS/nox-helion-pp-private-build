echo "C300: w_c5"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/h2.py <<'P'
from playwright.sync_api import sync_playwright
import json
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});seen={}
    pg.on('response',lambda r:seen.__setitem__(r.url.split('18091')[-1][:60],r.status) if '/api/' in r.url else None)
    pg.goto('http://127.0.0.1:18091/web/index.html',wait_until='load',timeout=60000);pg.wait_for_timeout(8000)
    print(json.dumps(seen,ensure_ascii=False))
    print(pg.evaluate("""()=>{var o=[];document.querySelectorAll('*').forEach(e=>{if(e.children.length==0&&/HOLD/.test(e.textContent||'')&&e.textContent.length<60)o.push(e.tagName+'#'+e.id+'.'+String(e.className).slice(0,40)+'|'+e.textContent.trim())});return o.slice(0,6)}"""))
    print(pg.evaluate("[...document.querySelectorAll('a[aria-label*=измерения]')].map(a=>a.innerText.replace(/\\s+/g,' '))"))
    b.close()
P
timeout 100 $N/venv/bin/python -W ignore /tmp/h2.py 2>&1 | cut -c1-1500
cd /workspace/nox/web/site; grep -l "· HOLD\|' · '+\|HOLD'" nox-*.js | head; grep -o ".\{0,160\}NOX HELION · .\{0,160\}" nox-shared-chrome-v10.js nox-connection-v13.js nox-home-flow.js 2>/dev/null | head -3 | cut -c1-400
