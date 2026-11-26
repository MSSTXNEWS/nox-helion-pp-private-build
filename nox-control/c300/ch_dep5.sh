echo "C300: ch_dep5"
S=/workspace/nox/web/site; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1
curl -fsSL --retry 5 --retry-all-errors "$R/nox-chat-clean.css?cb=$cb" -o /tmp/ch5.css || { echo FAIL; exit 0; }
grep -q "fix5:" /tmp/ch5.css || { echo STALE; exit 0; }
cp $S/nox-chat-clean.css $S/nox-chat-clean.css.bak_ch5_$cb; cp /tmp/ch5.css $S/nox-chat-clean.css
sed -i 's#nox-chat-clean.css?v=[0-9a-z]*#nox-chat-clean.css?v=ch5#' $S/chat.html; grep -o "nox-chat-clean[^\"]*" $S/chat.html
echo "== theme default in js"; grep -l "nox.ui.theme" $S/nox-chat*.js $S/nox-k*.js 2>/dev/null | head; grep -o "nox.ui.theme[^;]\{0,60\}" $S/nox-chat-*.js 2>/dev/null | head -5
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb")
cmp $S/nox-chat-clean.css /workspace/nox/web/pkg/webroot/nox-chat-clean.css && echo css_in_webroot; cmp $S/sw.js /workspace/nox/web/pkg/webroot/sw.js && echo sw_in_webroot; cmp $S/chat.html /workspace/nox/web/pkg/webroot/chat.html && echo chat_in_webroot
