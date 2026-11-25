echo "C300: ux_insp4"
S=/workspace/nox/web/site; cd $S
grep -c "nox-k4-core" system.html; grep -o "nox-k[46]-[a-z]*\.js[^\"]*" system.html | head -5; grep -c "ux-fab-js" nox-k4-core.js; ls -la nox-ux-fab.js | cut -c20-90
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
cat > /tmp/i4.py <<'PYX'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch();g=b.new_page(viewport={'width':1440,'height':900});er=[]
    g.on('pageerror',lambda e:er.append(str(e)[:100]))
    g.goto('http://127.0.0.1:8091/system.html',wait_until='load');g.wait_for_timeout(9000)
    print(g.url,g.evaluate("()=>({k4:typeof K4,fab:!!document.getElementById('k4-fab'),ux:!!document.getElementById('ux-fab'),uxjs:!!document.getElementById('ux-fab-js'),k4css:!!document.getElementById('k4-core-css')})"),er)
PYX
timeout 60 /workspace/nox/venv/bin/python /tmp/i4.py
