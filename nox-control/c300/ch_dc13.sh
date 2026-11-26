echo "C300: ch_dc13"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
for f in chat-dc.html nox-dc.css nox-dc.js nox-minichat.js; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "Цитата" /tmp/dc_nox-dc.js && grep -q "chat-dc.html" /tmp/dc_nox-minichat.js || { echo STALE; exit 0; }
[ -f $S/nox-minichat.js.bak_ch_dc ] || cp $S/nox-minichat.js $S/nox-minichat.js.bak_ch_dc
cp /tmp/dc_nox-dc.css $S/nox-dc.css; cp /tmp/dc_nox-dc.js $S/nox-dc.js; cp /tmp/dc_nox-minichat.js $S/nox-minichat.js
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for f in nox-dc.css nox-dc.js nox-minichat.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
