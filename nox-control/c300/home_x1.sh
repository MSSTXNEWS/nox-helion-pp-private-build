echo "K1: home_x1"
# Владелец 28.11 03:01: «Все заменяй и делай не жди» — новая главная вместо index.html.
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; cp -a $S/index.html /workspace/nox/state/web_bak_index_$cb.html; cp -a $S/index.html $S/index-old.html
curl -fsSL "$R/v3d/root/home.html?cb=$cb" -o /tmp/home.html && curl -fsSL "$R/v3d/v2/home.js?cb=$cb" -o /tmp/home.js || { echo DLFAIL; exit 0; }
grep -q "home.js" /tmp/home.html || { echo BAD_HOME; exit 0; }
cp /tmp/home.js $S/v2/home.js; cp /tmp/home.html $S/index.html; cp /tmp/home.html $S/home.html
echo "installed backup=web_bak_index_$cb old=index-old.html"
for u in index.html home.html index-old.html v2/home.js v2/kit.css; do echo "$u $(curl -s -o /dev/null -m 8 -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo "root $(curl -s -o /dev/null -m 8 -w %{http_code} http://127.0.0.1:18091/web/) gate $(curl -s -o /dev/null -m 8 -w %{http_code} -u owner:$(cat /workspace/nox/state/owner_gate/pass) http://127.0.0.1:18092/web/index.html)"
echo END
