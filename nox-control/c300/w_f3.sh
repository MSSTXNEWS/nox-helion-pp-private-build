echo "C300: w_f3"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js; curl -fsSL "$R/ch_dc1/nox-dc.css?cb=$t" -o /tmp/dc.css
 grep -q 'min-height:44px}.tb-i' /tmp/a11y.js && grep -q 'v12 (WEB)' /tmp/dc.css && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/a11y.js $S/nox-a11y-fix.js; cp /tmp/dc.css $S/nox-dc.css
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
for f in nox-a11y-fix.js nox-dc.css; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
wc -c $S/nox-theme.js
grep -E 'DONE' $N/agent/out/ui_sc.log | tail -2; ls $N/agent/out/ui_sc/*_lh.json 2>/dev/null | wc -l
