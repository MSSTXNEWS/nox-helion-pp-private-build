echo "C300: w_s1"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/ch_dc1/nox-dc-draw.js?cb=$t" -o /tmp/draw.js; grep -q 'data-nxg' /tmp/draw.js && grep -q 'function down' /tmp/draw.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/draw.js $S/nox-dc-draw.js
python3 - <<'P'
S='/workspace/nox/web/site/'
h=open(S+'chat-dc.html').read()
if 'nox-dc-draw.js' not in h:
    k='<script src="./nox-dc-cols.js?v=dc11" defer></script>'
    assert k in h
    open(S+'chat-dc.html.bak_w_s1','w').write(h)
    open(S+'chat-dc.html','w').write(h.replace(k,k+'\n<script src="./nox-dc-draw.js?v=dr1" defer></script>',1)); print('chat-dc patched')
p=open(S+'nox-photo.js').read()
if 'nox.photo.open' not in p:
    i=p.rindex('})();')
    open(S+'nox-photo.js.bak_w_s1','w').write(p)
    open(S+'nox-photo.js','w').write(p[:i]+"  try { var __u = sessionStorage.getItem('nox.photo.open'); if (__u) { sessionStorage.removeItem('nox.photo.open'); mount(__u); } } catch (e) {}\n"+p[i:]); print('photo patched')
P
node -e "new Function(require('fs').readFileSync('$S/nox-photo.js','utf8'))" && echo photo_js_ok
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/s1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-draw-s1')");pg.reload();pg.wait_for_timeout(3000)
    print('wrapped',pg.evaluate("/nxg/.test(String(document.querySelector('deep-chat').connect.handler))"))
    pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'нарисуй простой красный круг на белом фоне'})")
    for i in range(110):
        if pg.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.nxg')"):break
        pg.wait_for_timeout(2000)
    print('card',pg.evaluate("(()=>{const r=document.querySelector('deep-chat').shadowRoot;const c=r.querySelector('.nxg');if(!c)return (r.querySelector('#messages')||{}).innerText.slice(-200);const i=c.querySelector('img');return [i.getAttribute('src').slice(0,60),i.complete,i.naturalWidth]})()"),errs)
    b.close()
P
timeout 230 $N/venv/bin/python /tmp/s1.py 2>&1 | cut -c1-300
