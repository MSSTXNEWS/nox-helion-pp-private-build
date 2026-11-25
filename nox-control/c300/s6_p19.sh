echo S4RUN:s6_p19
cd /workspace/nox/web/site
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
cat > /tmp/m.py <<'PY'
import time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for i in range(3):
        pg=b.new_page(viewport={'width':1440,'height':900});errs=[]
        pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
        t=time.time();pg.goto('http://127.0.0.1:8091/web/music.html',wait_until='load')
        pg.wait_for_timeout(2500)
        print('load',round(time.time()-t-2.5,2),'errs',errs[:2],'vis',pg.evaluate("document.querySelectorAll('[style*=\"--cv:\"].vis').length"),'all',pg.evaluate("document.querySelectorAll('[style*=\"--cv:\"]').length"))
    b.close()
PY
/workspace/nox/venv/bin/python /tmp/m.py 2>&1 | tail -6
