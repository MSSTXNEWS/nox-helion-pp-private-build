echo "C300: ch_dep2"
S=/workspace/nox/web/site; cb=$(date +%s)
curl -fsSL --retry 5 --retry-all-errors "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/nox-chat-clean.css?cb=$cb" -o /tmp/ch2.css && grep -q "popover: ровные 32px" /tmp/ch2.css || { echo STALE; exit 0; }
cp $S/nox-chat-clean.css $S/nox-chat-clean.css.bak_ch2_$cb; cp /tmp/ch2.css $S/nox-chat-clean.css
sed -i 's#nox-chat-clean.css?v=[0-9a-z]*#nox-chat-clean.css?v=ch2#' $S/chat.html; grep -o "nox-chat-clean.css[^\"]*" $S/chat.html; echo deployed $cb
