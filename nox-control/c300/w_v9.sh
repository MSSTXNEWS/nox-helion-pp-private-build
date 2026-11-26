echo "C300: w_v9"
N=/workspace/nox
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/v8.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox'])
    pg=b.new_page(viewport={'width':390,'height':844})
    try: pg.goto('http://127.0.0.1:18091/web/studio.html',wait_until='load',timeout=60000)
    except Exception as e: print('goto',str(e)[:40])
    pg.wait_for_timeout(9000)
    print('scrollers',pg.evaluate("""()=>[...document.querySelectorAll('*')].filter(e=>{const cs=getComputedStyle(e);return /auto|scroll/.test(cs.overflowX)&&e.scrollWidth>e.clientWidth+5&&e.offsetParent&&!e.closest('#noxSharedHeaderV10')}).slice(0,6).map(e=>{const c=e.firstElementChild;return e.tagName+'.'+String(e.className).slice(0,24)+'#'+e.id+' cw='+e.clientWidth+' sw='+e.scrollWidth+' child='+(c?c.tagName+'.'+String(c.className).slice(0,20)+' w='+Math.round(c.getBoundingClientRect().width)+' fs='+getComputedStyle(c).flexShrink+' txt='+(c.textContent||'').trim().slice(0,12):'-')})"""))
    b.close()
P
timeout 150 $N/venv/bin/python /tmp/v8.py 2>&1 | cut -c1-700
