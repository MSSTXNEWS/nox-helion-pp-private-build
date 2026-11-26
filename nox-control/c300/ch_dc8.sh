echo "C300: ch_dc8"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
for f in chat-dc.html nox-dc.css nox-dc.js dcqa.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "function lab" /tmp/dc_nox-dc.js || { echo STALE; exit 0; }
cp /tmp/dc_chat-dc.html $S/chat-dc.html; cp /tmp/dc_nox-dc.css $S/nox-dc.css; cp /tmp/dc_nox-dc.js $S/nox-dc.js
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for f in chat-dc.html nox-dc.css nox-dc.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
setsid -f bash -c "timeout 600 $N/venv/bin/python /tmp/dc_dcqa.py > $N/agent/out/dcqa.out 2>&1" </dev/null >/dev/null 2>&1; echo qa_started
