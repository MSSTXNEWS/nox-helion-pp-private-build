echo "C300: w_i4"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_photo/nox-photo-dc.js?cb=$t" -o /tmp/pdc.js; curl -fsSL "$R/w_index/nox-index-fix.js?cb=$t" -o /tmp/ixf.js
 grep -q 'aria-label.*Отправить' /tmp/pdc.js && grep -q 'XMLHttpRequest' /tmp/ixf.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/pdc.js $S/nox-photo-dc.js; cp /tmp/ixf.js $S/nox-index-fix.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
for f in nox-photo-dc.js nox-index-fix.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py; curl -fsSL "$R/w_a11y/diag_page.py?cb=$(date +%s)" -o /tmp/diag_page.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 100 $N/venv/bin/python /tmp/axe_scan.py index photo 2>&1 | cut -c1-330
timeout 60 $N/venv/bin/python /tmp/diag_page.py index 2>&1 | sed 's/.*BAD/BAD/' | cut -c1-330
export PATH=$N/tools/node/bin:$PATH
rm -f $N/agent/out/ui_sc/{index,photo,tv,live,studio}_*
timeout 200 $N/venv/bin/python $N/tools/uiscore/score.py own index photo tv live studio 2>&1 | tail -2
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^(index|photo|tv|live|studio) ' | cut -c1-170
