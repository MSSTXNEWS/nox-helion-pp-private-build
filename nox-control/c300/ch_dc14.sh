echo "C300: ch_dc14"
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/webroot
for f in chat-dc.html nox-dc.js nox-dc.css nox-minichat.js; do echo "$f site=$(wc -c <$S/$f) pkg=$(wc -c <$P/$f) $(grep -c 'Цитата\|MINI\|chat-dc.html' $S/$f)"; done
grep -c "CH-DC" $S/chat.html $P/chat.html; wc -c $S/nox-theme.js
echo "--dc11"; cut -c1-500 /workspace/nox/agent/out/dcqa.out
