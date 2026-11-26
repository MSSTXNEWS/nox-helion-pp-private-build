echo "C300: w_q4"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js; grep -q 'html body nav.nox-worlds-control a.nox-worlds-open' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-a11y-fix.js $S/nox-a11y-fix.js.bak_q4; cp /tmp/a11y.js $S/nox-a11y-fix.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
mkdir -p /tmp/w18; curl -fsSL "$R/w_a11y/small_scan2.py?cb=$(date +%s)" > /tmp/w18/small_scan2.py
timeout 150 $N/venv/bin/python /tmp/w18/small_scan2.py photo settings system tv 2>&1 | cut -c1-300
