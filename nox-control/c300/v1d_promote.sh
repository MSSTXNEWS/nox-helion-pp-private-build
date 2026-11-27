echo "K1: v1d_promote"
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v1dpromote_$(date +%s); mkdir -p $T
[ -f $S/chat-v1d.html ] && [ -f $S/ab1d/ab.js ] || { echo "NO v1d on server"; exit 0; }
cp -a $S/chat-dc.html $T/chat-dc.html; echo "backup $T"
[ -f $S/chat-dc-jarvis.html ] || cp -a $S/chat-dc.html $S/chat-dc-jarvis.html
cp $S/chat-v1d.html $S/chat-dc.html
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite
bash <(curl -fsSL "$R/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/webroot_sync.sh?cb=$(date +%s)") | tail -1
for u in chat-dc.html chat-dc-jarvis.html chat-v1d.html chat-v1c.html ab1d/ab.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo "dc has ab1d: $(grep -c ab1d $S/chat-dc.html)"
