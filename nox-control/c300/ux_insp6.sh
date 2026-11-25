echo "C300: ux_insp6"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
cat > /tmp/i5.py <<'PYX'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch();g=b.new_page(viewport={'width':1440,'height':900});rs=[]
    g.on('response',lambda r:rs.append((r.status,r.url[-40:],r.headers.get('content-type','')[:25])) if 'k4' in r.url or 'k6-dash' in r.url else None)
    g.on('console',lambda m:print('C',m.type,m.text[:120]) if m.type in('error','warning') else None)
    g.goto('http://127.0.0.1:8091/web/system.html',wait_until='networkidle');g.wait_for_timeout(5000)
    print(g.url,rs,g.title()); print(g.evaluate("()=>[...document.scripts].filter(s=>/k4|k6/.test(s.src)).map(s=>s.src.slice(-30)+':'+s.defer)"), g.evaluate("typeof K4+' '+typeof K6dash"))
PYX
timeout 80 /workspace/nox/venv/bin/python /tmp/i5.py
