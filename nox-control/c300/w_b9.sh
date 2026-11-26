echo "C300: w_b9"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_index/nox-index-fix.js?cb=$t" -o /tmp/ixf.js; grep -q "removeAttribute('role')" /tmp/ixf.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/ixf.js $S/nox-index-fix.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/nox-index-fix.js $N/web/pkg/webroot/nox-index-fix.js && echo synced_ixf
mkdir -p /tmp/w18; for f in axe_scan small_scan2; do curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" | sed 's/127.0.0.1:8091/127.0.0.1:18091/g' > /tmp/w18/$f.py; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 100 $N/venv/bin/python /tmp/w18/axe_scan.py index 2>&1 | cut -c1-400
timeout 100 $N/venv/bin/python /tmp/w18/small_scan2.py index 2>&1 | cut -c1-600 | head -14
export PATH=$N/tools/node/bin:$PATH
sed 's#127.0.0.1:8091#127.0.0.1:18091#g' $N/tools/uiscore/score.py > $N/tools/uiscore/score18.py
rm -f $N/agent/out/ui_sc/index_*
timeout 120 $N/venv/bin/python $N/tools/uiscore/score18.py own index 2>&1 | tail -1
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^index ' | cut -c1-170
rm -f $N/tools/uiscore/score18.py
