echo "C300: w_q3"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/q3.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});pg.goto('http://127.0.0.1:18091/web/photo.html',wait_until='load');pg.wait_for_timeout(5000)
    print(pg.evaluate("""()=>[...document.querySelectorAll('.nox-worlds-open')].map(e=>{var c=getComputedStyle(e);var r=e.getBoundingClientRect();var par=e.parentElement,pc=getComputedStyle(par);return JSON.stringify([e.outerHTML.slice(0,160),c.display,c.height,c.minHeight,c.maxHeight,c.transform,c.zoom,r.height,par.tagName+'.'+par.className,pc.display,pc.transform,pc.zoom,pc.height,pc.overflow])})"""))
    b.close()
P
timeout 90 $N/venv/bin/python /tmp/q3.py 2>&1 | cut -c1-900
