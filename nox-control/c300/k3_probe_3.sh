echo "C300: k3_probe_3"
S=/workspace/nox/web/site; cd $S
echo "== minichat parse"; sed -n 28,48p nox-minichat.js | cut -c1-420
echo "== fin"; grep -n "fiC1\|fiC2\|fiCat\|fiList\|echarts\|uPlot\|svg" nox-fin-s1.js | cut -c1-360 | head -14
echo "== cmd"; grep -n "reg\[\|reg.set\|register\|chat.send\|'chat" nox-cmd.js | head -12 | cut -c1-200
echo "== file input"; grep -n "id=\"file\"\|btnAttach" chat.html | cut -c1-300; grep -n "'file'\|#file\|getElementById('file')" nox-chat-x.js | head -5 | cut -c1-240
echo "== chat bar"; grep -o '<div class="ctb"[^>]*>.\{0,500\}' chat.html | head -2
echo "== kn page"; sed -n 30,34p knowledge.html | cut -c1-500
echo "== qa tail"; sed -n 8,40p /tmp/k2_qa.py
exit 0
