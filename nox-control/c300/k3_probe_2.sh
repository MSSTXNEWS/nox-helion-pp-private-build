echo "C300: k3_probe_2"
S=/workspace/nox/web/site; cd $S
echo "== chatfx orb"; sed -n 30,84p nox-chat-fx.js | cut -c1-260
echo "== voice html"; cat voice.html | tail -c 1800
echo "== fin"; grep -o "class=\\\\\?\"[a-z0-9 _-]*\|echarts[^;]\{0,60\}\|id=\\\\\?\"[a-zA-Z0-9]*" nox-fin-s1.js | sort | uniq -c | sort -rn | head -30; wc -c nox-fin-s1.js
echo "== know"; grep -n "livebody\|innerHTML" knowledge.html | head -8 | cut -c1-300
echo "== news"; grep -o "className *= *'[^']*'\|class=\\\\\?\"[a-z0-9 _-]*" nox-s2-news.js | sort | uniq -c | sort -rn | head -20; grep -n "href\|<a " nox-s2-news.js | head -5 | cut -c1-240
echo "== readability"; ls vendor/readability; ls vendor/html-to-image
echo "== cmd names"; grep -o "'chat\.[a-z]*'\|'[a-z]*\.[a-z]*'" nox-cmd.js | sort -u | head -40 | tr '\n' ' '
echo "== api chat"; grep -n "api/chat" nox-minichat.js | head -3 | cut -c1-300
exit 0
