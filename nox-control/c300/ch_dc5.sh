echo "C300: ch_dc5"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
for f in nox-dc.css nox-dc.js; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "0.35vw" /tmp/dc_nox-dc.js || { echo STALE; exit 0; }
cp /tmp/dc_nox-dc.css $S/nox-dc.css; cp /tmp/dc_nox-dc.js $S/nox-dc.js
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for f in nox-dc.css nox-dc.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
echo "== ui score"; tail -5 $N/agent/out/dc_ui.log | cut -c1-300; for f in $N/agent/out/ui_sc/chat-dc_*.json; do echo $f; head -c 900 $f; echo; done
