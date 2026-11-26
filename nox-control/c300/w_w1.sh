echo "C300: w_w1"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
for k in 1 2 3 4 5 6 7 8; do curl -fsSL "$R/w_writer/nox-writer-pro.js?cb=$(date +%s)$k" -o /tmp/wr.js; grep -q 'order:9' /tmp/wr.js && break; sleep 15; done
grep -q 'order:9' /tmp/wr.js || { echo STALE; exit 0; }
cp /tmp/wr.js $S/nox-writer-pro.js
grep -q nox-writer-pro $S/writer.html || python3 - <<'P'
p='/workspace/nox/web/site/writer.html';s=open(p,encoding='utf-8').read()
i=s.rindex('</body>');open(p,'w',encoding='utf-8').write(s[:i]+'<script src="./nox-writer-pro.js?v=1" defer></script>\n'+s[i:])
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/writer.html $N/web/pkg/webroot/writer.html && cmp $S/nox-writer-pro.js $N/web/pkg/webroot/nox-writer-pro.js && echo synced
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 150 $N/venv/bin/python /tmp/axe_scan.py writer 2>&1 | cut -c1-900
cat > /tmp/wchk.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch();pg=b.new_page(viewport={'width':1920,'height':1080})
    pg.on('pageerror',lambda e:print('JSERR',str(e)[:150]))
    pg.goto('http://127.0.0.1:8091/web/writer.html');pg.wait_for_timeout(5000)
    print('book',pg.evaluate("!!document.querySelector('#wr-book sl-tab-group')"),pg.evaluate("document.querySelectorAll('#wr-ch .wr-i').length"))
P
timeout 60 $N/venv/bin/python /tmp/wchk.py 2>&1 | tail -3
