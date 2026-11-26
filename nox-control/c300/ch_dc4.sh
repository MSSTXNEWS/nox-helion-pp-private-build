echo "C300: ch_dc4"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
for f in nox-dc.css nox-dc.js pwdc.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "dcFirst" /tmp/dc_nox-dc.js || { echo STALE; exit 0; }
cp /tmp/dc_nox-dc.css $S/nox-dc.css; cp /tmp/dc_nox-dc.js $S/nox-dc.js
echo "== theme diag"; wc -c $S/nox-theme.js $N/web/pkg/webroot/nox-theme.js; curl -s http://127.0.0.1:8091/web/nox-theme.js | head -c 200; echo; curl -s -o /dev/null -w "graphite.css:%{http_code}\n" http://127.0.0.1:8091/web/nox-graphite.css
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -4
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -2
for f in nox-dc.css nox-dc.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
echo "== load"; uptime; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null
echo "== turn timing (qa-)"
for i in 1 2 3; do s=$(date +%s.%N); curl -sN -m 90 -X POST http://127.0.0.1:8091/api/turn -H 'Content-Type: application/json' -d "{\"conversation_id\":\"qa-dct$i\",\"message\":\"как дела\",\"mode\":\"auto\",\"length\":\"normal\",\"source\":\"full\"}" | while read -r l; do case "$l" in *'"t": "delta"'*|*'"t":"delta"'*) [ -z "$f1" ] && { f1=1; echo "first $(echo "$(date +%s.%N) - $s" | bc)"; };; *'"t": "done"'*|*'"t":"done"'*) echo "done $(echo "$(date +%s.%N) - $s" | bc)";; esac; done; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
NOXPORT=8091 timeout 150 $N/venv/bin/python /tmp/dc_pwdc.py 2>&1 | cut -c1-400
cat > /tmp/dc_ui.sh <<'B'
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
T=/workspace/nox/tools/uiscore; L=/workspace/nox/agent/out/dc_ui.log; : > $L
/workspace/nox/venv/bin/python $T/score.py own chat-dc >> $L 2>&1
/workspace/nox/venv/bin/python $T/score.py lh chat-dc >> $L 2>&1
echo DONE >> $L
B
[ -f $N/tools/uiscore/score.py ] && setsid -f bash /tmp/dc_ui.sh </dev/null >/dev/null 2>&1 && echo ui_score_started
