S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== VT1"; grep -n "startViewTransition" $S/*.js | cut -c1-220
cat > /tmp/s3_vt1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page()
    pg.on('pageerror',lambda e: print('R: pageerror',str(e)[:100],'|',(getattr(e,'stack','') or '')[:200].replace('\n',' ')))
    pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(2500)
    pg.evaluate("()=>{[...document.querySelectorAll('.tb a')].find(a=>/constructor|dispatcher|downloads/.test(a.getAttribute('href')||'')).click()}"); pg.wait_for_timeout(3000)
    b.close()
P
timeout 60 $PY -I /tmp/s3_vt1.py 2>&1 | cut -c1-400
