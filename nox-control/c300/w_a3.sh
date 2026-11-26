echo "C300: w_a3"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
sleep 25
curl -fsSL --retry 5 --retry-all-errors "$R/w_a11y/nox-a11y-fix.js?cb=$cb" -o /tmp/a11y.js || { echo FAIL; exit 0; }
grep -q 'a11y-fix' /tmp/a11y.js || { echo STALE; exit 0; }
cp /tmp/a11y.js $S/nox-a11y-fix.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
cmp $S/nox-a11y-fix.js $N/web/pkg/webroot/nox-a11y-fix.js && echo synced
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$cb" -o /tmp/axe_scan.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 180 $N/venv/bin/python /tmp/axe_scan.py settings photo calendar 2>&1 | cut -c1-900
