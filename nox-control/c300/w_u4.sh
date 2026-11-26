echo "C300: w_u4"
N=/workspace/nox
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/u4.py <<'P'
import time
from playwright.sync_api import sync_playwright
def run(b,q):
    pg=b.new_page(viewport={'width':1440,'height':900});pend={};done=[];t0=time.time()
    pg.on('request',lambda r:pend.__setitem__(r,time.time()-t0))
    def fin(r):
        if r in pend: done.append((round(time.time()-t0-pend[r],1),r.url.split('?')[0][-48:])); pend.pop(r,None)
    pg.on('requestfinished',fin);pg.on('requestfailed',fin)
    loaded=[None];pg.on('load',lambda *_:loaded.__setitem__(0,round(time.time()-t0,1)))
    try: pg.goto('http://127.0.0.1:18091/web/chat-dc.html'+q,wait_until='commit',timeout=30000)
    except Exception as e: print('goto',str(e)[:60])
    pg.wait_for_timeout(20000)
    print('Q',q,'load',loaded[0],'pending',[(round(time.time()-t0-v,1),r.url.split('?')[0][-48:]) for r,v in pend.items()][:8],'slow',sorted(done,reverse=True)[:5],'n',len(done))
    pg.close()
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    run(b,'?live=0&dcfix=0&agenda=0&draw=0&tiles=0'); run(b,'')
    b.close()
P
timeout 200 $N/venv/bin/python /tmp/u4.py 2>&1 | cut -c1-600
