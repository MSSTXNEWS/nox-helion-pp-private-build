echo "C300: w_b12"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/d2.py <<'P'
from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});pg.goto('http://127.0.0.1:18091/web/index.html',wait_until='load',timeout=60000);pg.wait_for_timeout(4000)
    print(pg.evaluate("""()=>[...document.querySelectorAll('a[aria-label*="открыть измерения"]')].map(a=>JSON.stringify([a.getAttribute('aria-label'),a.textContent,a.innerText,a.children.length]))"""))
    pg.close()
    pg=b.new_page(viewport={'width':390,'height':844});pg.goto('http://127.0.0.1:18091/web/index.html',wait_until='load',timeout=60000);pg.wait_for_timeout(4000)
    print(pg.evaluate("""()=>[...document.querySelectorAll('.nox-graphic-control')].slice(0,3).map(e=>{var c=getComputedStyle(e);return JSON.stringify([e.tagName,e.getAttribute('style'),c.minHeight,c.height,c.boxSizing,e.getBoundingClientRect().height,e.className])})"""))
    pg.close()
    for i in (1,2):
        for w,h in ((1440,900),(390,844)):
            pg=b.new_page(viewport={'width':w,'height':h});pg.goto('http://127.0.0.1:18091/web/index.html?ixfix=0',wait_until='load',timeout=60000);pg.wait_for_timeout(5000);pg.screenshot(path='/tmp/n_%d_%d.png'%(w,i));pg.close()
    b.close()
for w in (1440,390):
    a=Image.open('/tmp/n_%d_1.png'%w).convert('L');c=Image.open('/tmp/n_%d_2.png'%w).convert('L')
    d=ImageChops.difference(a,c).point(lambda v:255 if v>40 else 0);print('noise',w,round(sum(1 for v in d.getdata() if v)/(a.size[0]*a.size[1])*100,2),'%')
P
timeout 150 $N/venv/bin/python -W ignore /tmp/d2.py 2>&1 | cut -c1-900
