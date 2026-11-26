echo "C300: ch_dc18"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
curl -fsSL --retry 5 "$R/nox-minichat.js?cb=$cb" -o /tmp/dc_mc.js && grep -q "max-width:768px" /tmp/dc_mc.js || { echo STALE; exit 0; }
cp /tmp/dc_mc.js $S/nox-minichat.js
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
cmp $S/nox-minichat.js $N/web/pkg/webroot/nox-minichat.js && echo synced_mc
wc -c $S/nox-theme.js
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/m2.py <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch();pg=b.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
    pg.goto('http://127.0.0.1:8091/web/settings.html',wait_until='load');pg.wait_for_timeout(4000)
    print('fab',pg.evaluate("(()=>{const f=document.querySelector('.nmc-fab');const r=f.getBoundingClientRect();const t=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return [Math.round(r.x),Math.round(r.y),Math.round(r.width),t===f]})()"))
    pg.tap('.nmc-fab');pg.wait_for_timeout(3000);print('open',pg.evaluate("!document.querySelector('.nmc').hidden"))
PY
timeout 60 $N/venv/bin/python /tmp/m2.py 2>&1 | tail -3 | cut -c1-200
echo "== dcqa"; cut -c1-700 $N/agent/out/dcqa.out
