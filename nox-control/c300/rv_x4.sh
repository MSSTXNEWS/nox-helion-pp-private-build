echo "K1: rv_x4"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_rv4_$cb; mkdir -p $T
for f in pdf.html editor.html; do [ -f $S/$f ] && cp -a $S/$f $T/ && sed -i 's/<div class="ed-tabs" role="tablist"/<div class="ed-tabs" role="group"/' $S/$f && echo "$f $(grep -c 'ed-tabs" role="group"' $S/$f)"; done
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for p in pdf editor; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/$p.html)"; done
