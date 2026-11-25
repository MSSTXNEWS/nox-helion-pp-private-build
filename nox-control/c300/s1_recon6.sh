S=/workspace/nox/web/site
cd $S
grep -ln "streamTurn" *.js | head
F=$(grep -ln "function streamTurn\|streamTurn *=" *.js | head -1); echo FILE $F
grep -n "streamTurn" $F | head -3 | cut -c1-200
grep -on "\(fetch\|new URL\|BASE\|ROOT\)[^;]\{0,140\}" $F | head -30
sed -n 45,52p nox-nav-x.js | cut -c1-500
sed -n 66,74p nox-pult.js | cut -c1-300
echo ==MODEJS; ls nox_mode.js nox-mode.js 2>&1; grep -n "script" chat.html | grep -i mode
echo ==WEBROOT; grep -n "_ctx\|/web/\|ROOT *=" /workspace/nox/web/pkg/server/web_server.py | sed -n 1,25p | cut -c1-200
