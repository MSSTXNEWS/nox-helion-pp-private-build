echo "C300: w_x2"
N=/workspace/nox
cat > /tmp/xchk2.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch();pg=b.new_page(viewport={'width':1440,'height':900});pg.on('pageerror',lambda e:print('JSERR',str(e)[:100]))
    pg.goto('http://127.0.0.1:8091/web/writer.html?role=scientist');pg.wait_for_timeout(5000)
    pg.evaluate("window.NOXroleStudio.cm.setValue('Энергия $E=mc^2$')")
    pg.click('sl-button:has-text("Просмотр")');pg.wait_for_timeout(2500)
    print('sci media',pg.evaluate("!!document.querySelector('#rs-media')"),'katex',pg.evaluate("document.querySelectorAll('#rs-pvb .katex').length"))
    pg.evaluate("window.NOXroleStudio.cm.setValue('')")
P
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 100 $N/venv/bin/python /tmp/xchk2.py 2>&1 | tail -4
