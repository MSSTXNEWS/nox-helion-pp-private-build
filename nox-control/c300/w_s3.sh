echo "C300: w_s3"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/s3.py <<'P'
from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});errs=[];reqs=[];t0=time.time()
    pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
    pg.on('request',lambda r:reqs.append('%d %s'%(time.time()-t0,r.url.split('18091')[-1][:40])) if any(k in r.url for k in ('/img/','api/chat','api/turn')) else None)
    pg.on('response',lambda r:reqs.append('  -> %s %s'%(r.status,r.url.split('18091')[-1][:30])) if '/img/generate' in r.url else None)
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-draw-s3')");pg.reload();pg.wait_for_timeout(5000)
    print('wrapper',pg.evaluate("String(document.querySelector('deep-chat').connect.handler).includes('RX')||String(document.querySelector('deep-chat').connect.handler).includes('improve')"))
    pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'нарисуй простой красный круг на белом фоне'})")
    for i in range(100):
        if pg.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.nxg')"):break
        pg.wait_for_timeout(2000)
    print('card',pg.evaluate("(()=>{const r=document.querySelector('deep-chat').shadowRoot;const c=r.querySelector('.nxg');if(!c)return 'NO CARD: '+r.querySelector('#messages').innerText.slice(-160).replace(/\\n/g,' | ');const i=c.querySelector('img');return [i.getAttribute('src').slice(0,50),i.complete,i.naturalWidth]})()"),errs)
    print(reqs[:10]);b.close()
P
timeout 230 $N/venv/bin/python /tmp/s3.py 2>&1 | cut -c1-400
