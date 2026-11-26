echo "C300: ch_dc12"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
for f in chat-dc.html nox-dc.css nox-dc.js nox-minichat.js; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "MINI" /tmp/dc_nox-dc.js && grep -q "chat-dc.html" /tmp/dc_nox-minichat.js || { echo STALE; exit 0; }
[ -f $S/nox-minichat.js.bak_ch_dc ] || cp $S/nox-minichat.js $S/nox-minichat.js.bak_ch_dc
cp /tmp/dc_nox-dc.css $S/nox-dc.css; cp /tmp/dc_nox-dc.js $S/nox-dc.js; cp /tmp/dc_nox-minichat.js $S/nox-minichat.js
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for f in nox-dc.css nox-dc.js nox-minichat.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/mini.py <<'PY'
import base64,textwrap
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for w,h,m in [(1920,1080,0),(390,844,1)]:
        pg=b.new_page(viewport={'width':w,'height':h},has_touch=bool(m),is_mobile=bool(m))
        pg.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
        pg.goto('http://127.0.0.1:8091/web/settings.html',wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-mini%d')"%w);pg.wait_for_timeout(3000)
        pg.click('.nmc-fab');pg.wait_for_timeout(5000)
        fr=pg.frames[-1];print(w,'frames',len(pg.frames),fr.url[-40:])
        fr.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'привет'})")
        for i in range(60):
            if fr.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.dc-acts-live')"):break
            pg.wait_for_timeout(1000)
        print(w,'reply',fr.evaluate("[...document.querySelector('deep-chat').shadowRoot.querySelectorAll('.ai-message-text')].pop().innerText.slice(0,80)"))
        pg.screenshot(path='/tmp/m%d.jpg'%w,type='jpeg',quality=40);d=base64.b64encode(open('/tmp/m%d.jpg'%w,'rb').read()).decode()
        print('B64BEGIN%d'%w);print('\n'.join(textwrap.wrap(d,170)));print('B64END%d'%w);pg.close()
PY
timeout 200 $N/venv/bin/python /tmp/mini.py 2>&1 | cut -c1-300
