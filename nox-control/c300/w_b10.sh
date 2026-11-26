echo "C300: w_b10"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
N=/workspace/nox
cat > /tmp/hd.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});pg.goto('http://127.0.0.1:18091/web/index.html',wait_until='load',timeout=60000);pg.wait_for_timeout(4000)
    print(pg.evaluate("""()=>[...document.querySelectorAll('header,[role=banner]')].map(h=>({tag:h.tagName,id:h.id,cls:String(h.className).slice(0,50),role:h.getAttribute('role'),par:h.parentElement.tagName+'.'+String(h.parentElement.className).slice(0,30),txt:h.textContent.trim().slice(0,40),skip:!!document.querySelector('.helion-skip'),tgt:!!document.getElementById('homeChatTile'),skipPar:(document.querySelector('.helion-skip')||{parentElement:{tagName:''}}).parentElement.tagName,
    cs:[...document.querySelectorAll('.nox-shared-signature-v10,.nox-graphic-control,#nox-cinematic-light-cycle')].map(e=>e.tagName+'|'+getComputedStyle(e).minWidth+'|'+getComputedStyle(e).maxWidth+'|'+getComputedStyle(e).boxSizing+'|'+e.getBoundingClientRect().width.toFixed(1)).join(' ; ')}))"""))
    b.close()
P
timeout 80 $N/venv/bin/python /tmp/hd.py 2>&1 | cut -c1-1800
