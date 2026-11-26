echo "K1: rv_x3"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_rv3_$cb; mkdir -p $T
for f in nox-a11y-fix.js pdf.html atlas.html assistant.html $(cd $S && ls *-s1.main.html 2>/dev/null); do [ -f $S/$f ] && cp -a $S/$f $T/; done; echo "backup $T ($(ls $T|wc -l) files)"
curl -fsSL "$R/w_rv3/rvfix3.py?cb=$cb" -o /tmp/rvfix3.py && python3 /tmp/rvfix3.py $S
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for p in organism pdf atlas map qa cinema assistant chat-dc; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/$p.html)"; done
grep -c rvfix3 $S/nox-a11y-fix.js
