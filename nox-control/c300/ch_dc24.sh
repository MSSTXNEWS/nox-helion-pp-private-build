echo "C300: ch_dc24"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
sleep 25
for f in chat-dc.html nox-dc.css nox-dc.js nox-dc-cols.js dcqa.py dctest.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "NOXdcGlass" /tmp/dc_nox-dc.js && grep -q "dcGlassDock" /tmp/dc_chat-dc.html || { echo STALE; exit 0; }
for f in chat-dc.html nox-dc.css nox-dc.js nox-dc-cols.js; do cp /tmp/dc_$f $S/$f; done
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for f in chat-dc.html nox-dc.css nox-dc.js nox-dc-cols.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done; wc -c $S/nox-theme.js
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
setsid -f bash -c "timeout 900 $N/venv/bin/python /tmp/dc_dcqa.py > $N/agent/out/dcqa.out 2>&1" </dev/null >/dev/null 2>&1
timeout 200 $N/venv/bin/python /tmp/dc_dctest.py 2>&1 | cut -c1-400
