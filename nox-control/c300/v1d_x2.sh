echo "K1: v1d_x2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/v1d; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v1d_$cb; mkdir -p $T
for f in chat-v1d.html ab1d/ab.js ab1d/ab.css ab1d/skin.css ab1d/skin.js; do [ -f $S/$f ] && { mkdir -p $T/$(dirname $f); cp -a $S/$f $T/$f; }; done; echo "backup $T"
W=/tmp/v1d_$cb; mkdir -p $W; ok=0
for k in 1 2 3 4 5 6; do rm -rf $W/*; fail=0
 for f in chat-v1d.html ab.js ab.css skin.css skin.js; do curl -fsSL "$R/$f?cb=$cb$k" -o $W/$f || fail=1; done
 [ $fail = 0 ] && grep -q "api/nox/memory/" $W/ab.js && grep -q nox-credfix $W/ab.js && grep -q "DRAW|" $W/ab.js && grep -q "slice(0,140)" $W/ab.js && grep -q "korea_img_disabled" $W/ab.js && grep -q "nox-palette" $W/ab.js && grep -q "nox-listen" $W/ab.js && grep -q ab1d/skin.js $W/chat-v1d.html && grep -q ab1d/ab.js $W/chat-v1d.html && grep -q arwes-frames $W/skin.js && { ok=1; break; }; sleep 5; done
[ $ok = 1 ] || { echo STALE; exit 0; }
mkdir -p $S/ab1d; cp $W/ab.js $W/ab.css $W/skin.css $W/skin.js $S/ab1d/; cp $W/chat-v1d.html $S/
echo "installed credfix=$(grep -c nox-credfix $S/ab1d/ab.js) ab.js=$(wc -c <$S/ab1d/ab.js)B"
bash <(curl -fsSL "$R/../th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/../th_graphite/webroot_sync.sh?cb=$cb") | tail -1
cp -a $S/chat-dc.html $T/chat-dc.html; cp $S/chat-v1d.html $S/chat-dc.html
for u in chat-v1d.html ab1d/ab.js ab1d/ab.css ab1d/skin.css ab1d/skin.js chat-v1c.html chat-dc.html; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done

echo "dc has ab1d: $(grep -c ab1d $S/chat-dc.html) mem=$(grep -c api/nox/memory/ $S/ab1d/ab.js)"
