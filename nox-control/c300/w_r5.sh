echo "C300: w_r5"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/th_graphite/nox-graphite.css?cb=$t" -o /tmp/g.css; curl -fsSL "$R/th_graphite/nox-theme.js?cb=$t" -o /tmp/t.js
 grep -q TH-PALETTE-FOCUS /tmp/g.css && grep -q 'TH-PALETTE' /tmp/t.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-graphite.css $S/nox-graphite.css.bak_r5; cp $S/nox-theme.js $S/nox-theme.js.bak_r5
cp /tmp/g.css $S/nox-graphite.css; cp /tmp/t.js $S/nox-theme.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
grep -c TH-PALETTE $S/nox-graphite.css $S/nox-theme.js
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/r5.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for n in ('settings','system','chat-dc','studio'):
        pg=b.new_page(viewport={'width':1440,'height':900});pg.goto('http://127.0.0.1:18091/web/%s.html'%n,wait_until='load',timeout=60000);pg.wait_for_timeout(3500)
        r=pg.evaluate("""()=>{const H=document.documentElement;const out={theme:H.getAttribute('data-nox-theme'),ls:localStorage.getItem('nox.ui.theme')};
          out.acc={};for(const p of ['gold','copper','ion']){H.setAttribute('data-nox-color',p);out.acc[p]=getComputedStyle(H).getPropertyValue('--gx-acc').trim()+'|'+getComputedStyle(H).getPropertyValue('--sl-color-primary-600').trim()}
          return out}""")
        print(n,r);pg.close()
    b.close()
P
timeout 100 $N/venv/bin/python /tmp/r5.py 2>&1 | cut -c1-400
