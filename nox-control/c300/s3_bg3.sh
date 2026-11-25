S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== BG3"
cat > /tmp/s3_bg3q.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/system.html',wait_until='load'); pg.wait_for_timeout(4500)
    print('R:',pg.evaluate("()=>[...document.querySelectorAll('#page .wrap > *, #page .wrap section, #page canvas')].slice(0,14).map(e=>{const s=getComputedStyle(e);return e.tagName+'.'+e.className.toString().slice(0,26)+' bf='+s.backdropFilter.slice(0,22)+' bg='+s.backgroundColor+' pos='+s.position}).join('\\n')"))
    b.close()
P
timeout 90 $PY -I /tmp/s3_bg3q.py 2>&1 | cut -c1-200
