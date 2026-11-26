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
