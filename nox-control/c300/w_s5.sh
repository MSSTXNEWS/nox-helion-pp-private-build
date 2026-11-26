echo "C300: w_s5"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/ch_dc1/nox-dc-draw.js?cb=$t" -o /tmp/draw.js; curl -fsSL "$R/ch_dc1/nox-dc.js?cb=$t" -o /tmp/dc.js
 grep -q 'window.NOXdcDraw = ' /tmp/draw.js && grep -q '0.9' /tmp/draw.js && grep -q 'NOXdcDraw(body' /tmp/dc.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
echo "server dc md5: $(md5sum < $S/nox-dc.js | cut -c1-32)"
if [ "$(md5sum < $S/nox-dc.js | cut -c1-32)" = "4cea80f8ca3c356ae4a8edc7f07c7642" ]; then cp $S/nox-dc.js $S/nox-dc.js.bak_w_s5; cp /tmp/dc.js $S/nox-dc.js; sed -i 's#nox-dc.js?v=dc11#nox-dc.js?v=dc12#' $S/chat-dc.html; echo DC_PATCHED; else echo DC_DIFFERS; fi
cp /tmp/draw.js $S/nox-dc-draw.js; sed -i 's#nox-dc-draw.js?v=dr1#nox-dc-draw.js?v=dr2#' $S/chat-dc.html
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/s5.py <<'P'
from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});errs=[];reqs=[];t0=time.time()
    pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
    pg.on('request',lambda r:reqs.append('%d %s'%(time.time()-t0,r.url.split('18091')[-1][:40])) if any(k in r.url for k in ('/img/','api/chat','api/turn')) else None)
    pg.on('response',lambda r:reqs.append('  -> %s %s'%(r.status,r.url.split('18091')[-1][:30])) if '/img/generate' in r.url else None)
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-draw-s5')");pg.reload();pg.wait_for_timeout(5000)
    print('wrapper',pg.evaluate("String(document.querySelector('deep-chat').connect.handler).includes('RX')||String(document.querySelector('deep-chat').connect.handler).includes('improve')"))
    pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'нарисуй простой красный круг на белом фоне'})")
    for i in range(100):
        if pg.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.nxg')"):break
        pg.wait_for_timeout(2000)
    print('card',pg.evaluate("(()=>{const r=document.querySelector('deep-chat').shadowRoot;const c=r.querySelector('.nxg');if(!c)return 'NO CARD: '+r.querySelector('#messages').innerText.slice(-160).replace(/\\n/g,' | ');const i=c.querySelector('img');return [i.getAttribute('src').slice(0,50),i.complete,i.naturalWidth]})()"),errs)
    print(reqs[:10]);b.close()
P
timeout 230 $N/venv/bin/python /tmp/s5.py 2>&1 | cut -c1-400
