echo "C300: ch_dep3"
S=/workspace/nox/web/site; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1
for f in nox-chat-clean.css nox-chat-clean.js; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/ch3_$f || { echo FAIL; exit 0; }; done
grep -q "pointer:coarse){" /tmp/ch3_nox-chat-clean.css && grep -q "k7-rel" /tmp/ch3_nox-chat-clean.js || { echo STALE; exit 0; }
cp $S/nox-chat-clean.css $S/nox-chat-clean.css.bak_ch3_$cb; cp $S/nox-chat-clean.js $S/nox-chat-clean.js.bak_ch3_$cb
cp /tmp/ch3_nox-chat-clean.css $S/nox-chat-clean.css; cp /tmp/ch3_nox-chat-clean.js $S/nox-chat-clean.js
sed -i 's#nox-chat-clean.css?v=[0-9a-z]*#nox-chat-clean.css?v=ch3#;s#nox-chat-clean.js?v=[0-9a-z]*#nox-chat-clean.js?v=ch3#' $S/chat.html; grep -o "nox-chat-clean[^\"]*" $S/chat.html; echo deployed $cb
echo "== golden"; cat /workspace/nox/state/ch_golden.out | cut -c1-200; ls -l /workspace/nox/state/ch_verified.json 2>&1
