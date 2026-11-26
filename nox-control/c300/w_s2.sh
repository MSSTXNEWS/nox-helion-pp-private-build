echo "C300: w_s2"
N=/workspace/nox; S=$N/web/site; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
grep -n "nox-dc" $S/chat-dc.html | cut -c1-160; ls -la $S/nox-dc-draw.js $N/web/pkg/webroot/nox-dc-draw.js | cut -c20-110
curl -s -m5 http://127.0.0.1:18091/web/chat-dc.html | grep -c nox-dc-draw
cat > /tmp/s2.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox']);pg=b.new_page();logs=[]
    pg.on('console',lambda m:logs.append(m.text[:100]));pg.on('pageerror',lambda e:logs.append('PE '+str(e)[:120]))
    pg.on('response',lambda r:logs.append('R %s %s'%(r.status,r.url.split('/web/')[-1][:40])) if 'draw' in r.url else None)
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.wait_for_timeout(4000)
    print(pg.evaluate("({c:!!document.querySelector('deep-chat').connect,h:String((document.querySelector('deep-chat').connect||{}).handler).slice(0,60),nx:!!window.NOXdc})"),logs[:8]);b.close()
P
timeout 60 $N/venv/bin/python /tmp/s2.py 2>&1 | cut -c1-500
