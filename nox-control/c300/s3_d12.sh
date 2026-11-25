S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== D12"; head -3 $S/sw.js | cut -c1-260
cat > /tmp/s3_d12.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for w in (900,1024,1100,1180,1280,1440,1920):
        ctx=b.new_context(viewport={'width':w,'height':900},service_workers='block'); pg=ctx.new_page()
        pg.goto('http://localhost:8091/web/music.html',wait_until='load'); pg.wait_for_timeout(2500)
        print('W',w, pg.evaluate("()=>{const r=[...document.querySelectorAll('.tb-l > *')].filter(c=>getComputedStyle(c).display!='none').map(c=>Math.round(c.getBoundingClientRect().left));const s=[...document.querySelectorAll('.tb-r > *')].filter(c=>getComputedStyle(c).display!='none').map(c=>Math.round(c.getBoundingClientRect().right));const c=document.getElementById('nxx-crumb');return [Math.min(...r),Math.max(...s),innerWidth,c&&c.textContent]}"))
        ctx.close()
    b.close()
P
timeout 150 $PY -I /tmp/s3_d12.py 2>&1 | cut -c1-200
