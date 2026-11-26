echo "C300: ch_dep4"
S=/workspace/nox/web/site; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1
for f in nox-chat-clean.css nox-chat-clean.js; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/ch4_$f || { echo FAIL; exit 0; }; done
grep -q "cw-notebtn" /tmp/ch4_nox-chat-clean.css && grep -q "cw-notebtn" /tmp/ch4_nox-chat-clean.js || { echo STALE; exit 0; }
cp $S/nox-chat-clean.css $S/nox-chat-clean.css.bak_ch4_$cb; cp $S/nox-chat-clean.js $S/nox-chat-clean.js.bak_ch4_$cb
cp /tmp/ch4_nox-chat-clean.css $S/nox-chat-clean.css; cp /tmp/ch4_nox-chat-clean.js $S/nox-chat-clean.js
sed -i 's#nox-chat-clean.css?v=[0-9a-z]*#nox-chat-clean.css?v=ch4#;s#nox-chat-clean.js?v=[0-9a-z]*#nox-chat-clean.js?v=ch4#' $S/chat.html; grep -o "nox-chat-clean[^\"]*" $S/chat.html; echo deployed $cb
tail -c 700 /workspace/nox/state/ch_audit1.log; pgrep -af qa_audit | cut -c1-100 | head -4
