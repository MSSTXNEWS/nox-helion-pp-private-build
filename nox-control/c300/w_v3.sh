echo "C300: w_v3"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6; do t=$(date +%s)$k
 curl -fsSL "$R/w_v3/live_shell.py?cb=$t" -o /tmp/lsh.py; curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js
 grep -q nxLiveWow /tmp/lsh.py && grep -q '#s2tv .top' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-a11y-fix.js $S/nox-a11y-fix.js.bak_v3; cp /tmp/a11y.js $S/nox-a11y-fix.js
python3 /tmp/lsh.py $S
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
