echo "C300: w_b11"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_index/nox-index-fix.js?cb=$t" -o /tmp/ixf.js; grep -q "wrapNav" /tmp/ixf.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/ixf.js $S/nox-index-fix.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/nox-index-fix.js $N/web/pkg/webroot/nox-index-fix.js && echo synced_ixf
mkdir -p /tmp/w18; for f in axe_scan small_scan2 diag_page; do curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" | sed 's/127.0.0.1:8091/127.0.0.1:18091/g' > /tmp/w18/$f.py; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 100 $N/venv/bin/python /tmp/w18/axe_scan.py index 2>&1 | cut -c1-400
timeout 100 $N/venv/bin/python /tmp/w18/small_scan2.py index 2>&1 | cut -c1-500 | head -6
timeout 60 $N/venv/bin/python /tmp/w18/diag_page.py index 2>&1 | sed 's/.*BAD/BAD/' | cut -c1-200
cat > /tmp/shot.py <<'P'
from playwright.sync_api import sync_playwright
import hashlib
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for w,h in ((1440,900),(390,844)):
        for q in ('?ixfix=0','?x=1'):
            pg=b.new_page(viewport={'width':w,'height':h});pg.goto('http://127.0.0.1:18091/web/index.html'+q,wait_until='load',timeout=60000);pg.wait_for_timeout(5000)
            pg.screenshot(path='/tmp/ix_%d_%s.png'%(w,'old' if 'fix=0' in q else 'new'));pg.close()
    b.close()
P
timeout 120 $N/venv/bin/python /tmp/shot.py 2>&1 | tail -2
$N/venv/bin/python - <<'P'
from PIL import Image, ImageChops
for w in (1440,390):
    a=Image.open('/tmp/ix_%d_old.png'%w).convert('L');b=Image.open('/tmp/ix_%d_new.png'%w).convert('L')
    d=ImageChops.difference(a,b).point(lambda v:255 if v>40 else 0);print('diff',w,round(sum(1 for v in d.getdata() if v)/ (a.size[0]*a.size[1])*100,2),'%')
P
export PATH=$N/tools/node/bin:$PATH
sed 's#127.0.0.1:8091#127.0.0.1:18091#g' $N/tools/uiscore/score.py > $N/tools/uiscore/score18.py
rm -f $N/agent/out/ui_sc/index_*
timeout 120 $N/venv/bin/python $N/tools/uiscore/score18.py own index 2>&1 | tail -1
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^index ' | cut -c1-170
rm -f $N/tools/uiscore/score18.py
