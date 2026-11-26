echo "C300: w_p3"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js; grep -q 'FIE_root button' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-a11y-fix.js $S/nox-a11y-fix.js.bak_p3; cp /tmp/a11y.js $S/nox-a11y-fix.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright PATH=$N/tools/node/bin:$PATH
timeout 100 $N/venv/bin/python /tmp/w18/small_scan2.py photo 2>&1 | cut -c1-400
for pg in photo; do rm -f $N/agent/out/ui_sc/${pg}_*; timeout 150 $N/venv/bin/python $N/tools/uiscore/score.py all $pg 2>&1 | tail -1; done
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^photo ' | cut -c1-170
