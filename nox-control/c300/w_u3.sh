echo "C300: w_u3"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6; do curl -fsSL "$R/w_u1/nox-t44.js?cb=$(date +%s)$k" -o /tmp/t44.js; grep -q noxSharedHeaderV10 /tmp/t44.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-t44.js $S/nox-t44.js.bak_u3; cp /tmp/t44.js $S/nox-t44.js; echo t44 updated
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
