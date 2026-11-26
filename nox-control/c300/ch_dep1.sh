echo "C300: ch_dep1"
N=/workspace/nox; S=$N/web/site; B=/tmp/ch_ui1; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1; cb=$(date +%s)
rm -rf $B; mkdir -p $B; for f in nox-chat-clean.css nox-chat-clean.js q10.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o $B/$f && [ -s $B/$f ] || { echo FAIL $f; exit 0; }; done
grep -q "v2 (CH)" $B/nox-chat-clean.css || { echo STALE_CSS; exit 0; }
node --check $B/nox-chat-clean.js 2>&1 | head -3 || true
TS=$(date +%s); cp $S/nox-chat-clean.css $S/nox-chat-clean.css.bak_ch_$TS; cp $S/nox-chat-clean.js $S/nox-chat-clean.js.bak_ch_$TS; cp $S/chat.html $S/chat.html.bak_ch_$TS
cp $B/nox-chat-clean.css $B/nox-chat-clean.js $S/
sed -i 's#nox-chat-clean.css?v=[0-9a-z]*#nox-chat-clean.css?v=ch1#;s#nox-chat-clean.js?v=[0-9a-z]*#nox-chat-clean.js?v=ch1#' $S/chat.html
grep -o "nox-chat-clean[^\"]*" $S/chat.html; curl -s -m5 localhost:8091/web/nox-chat-clean.css | grep -c "v2 (CH)"
echo "rollback: cp $S/nox-chat-clean.css.bak_ch_$TS ... ; ts=$TS"
setsid -f python3 $B/q10.py a1 > $N/state/ch_q10.out 2>&1 < /dev/null; echo started
