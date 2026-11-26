echo "C300: w_p2"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_perf/nox-nav.js?cb=$t" -o /tmp/nav.js; curl -fsSL "$R/w_perf/nox-ninja.js?cb=$t" -o /tmp/ninja.js
 grep -q PERF-LAZY /tmp/nav.js && grep -q PERF-LAZY /tmp/ninja.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cd $S; md5sum nox-nav.js nox-ninja.js
if [ "$(md5sum < nox-nav.js | cut -c1-32)" = "1d38ec41a47d5ead30a2075d8e826a4f" ] && [ "$(md5sum < nox-ninja.js | cut -c1-32)" = "760165f8f43ac849546c8faf5bf909ca" ]; then
 cp nox-nav.js nox-nav.js.bak_w_p2; cp nox-ninja.js nox-ninja.js.bak_w_p2; cp /tmp/nav.js nox-nav.js; cp /tmp/ninja.js nox-ninja.js; echo PATCHED
else echo "ORIG_DIFFERS (не трогаю)"; fi
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/nox-nav.js $N/web/pkg/webroot/nox-nav.js && echo synced_nav
mkdir -p /tmp/w18; for f in diag_page small_scan2; do curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" > /tmp/w18/$f.py; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 120 $N/venv/bin/python /tmp/w18/small_scan2.py photo settings system 2>&1 | cut -c1-600
timeout 90 $N/venv/bin/python /tmp/w18/diag_page.py settings system 2>&1 | cut -c1-180
