echo S4RUN:s6_recon3
cd /workspace/nox/web/site
echo "## NOXcmd/api usage"; for p in photo news cinema music studio creative board tv training projects calendar dispatcher system growth memory consciousness organism soul selffeel nexus; do echo "$p: $(grep -l 'NOXcmd\|api/chat' $p.html nox-s2-$p.js nox-s4-$p*.js 2>/dev/null | tr '\n' ' ')"; done
grep -n "NOXcmd" nox-actions.js | head -5; grep -n "window.NOXcmd\|NOXcmd *=" *.js 2>/dev/null | head -5
echo "## ds vars"; grep -o '\-\-ds-[a-z0-9-]*:[^;]*' nox-ds.css | sort -u | head -30
echo "## news js head"; head -c 3000 nox-s2-news.js
echo "## news css"; grep -n "nw-\|\.nw" nox-s2.css | head -40
