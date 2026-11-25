PY=/workspace/nox/venv/bin/python
echo "== BG5"
cat > /tmp/s3_bg5.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/system.html',wait_until='load'); pg.wait_for_timeout(4500)
    print('R:',pg.evaluate("()=>{const c=document.querySelectorAll('section.card.c6')[0];const s=getComputedStyle(c);return [s.backgroundColor,s.backgroundImage.slice(0,120),s.opacity,s.mixBlendMode,s.isolation,c.matches(':has(canvas)'),getComputedStyle(c,'::before').backgroundImage.slice(0,80),getComputedStyle(c,'::before').background.slice(0,100)]}"))
    b.close()
P
timeout 90 $PY -I /tmp/s3_bg5.py 2>&1 | cut -c1-500
