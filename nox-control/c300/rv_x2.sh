echo "C300: rv_x2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_rv2_$cb; mkdir -p $T
for f in nox-a11y-fix.js assistant.html; do [ -f $S/$f ] && cp -a $S/$f $T/; done; echo "backup $T"
curl -fsSL "$R/w_rv2/rvfix2.py?cb=$cb" -o /tmp/rvfix2.py && python3 /tmp/rvfix2.py $S
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for p in chat-dc writer settings studio assistant voice board calendar cinema; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/$p.html)"; done
grep -c rvfix2 $S/nox-a11y-fix.js; grep -c 'role="group" aria-label="Раздел"' $S/assistant.html
