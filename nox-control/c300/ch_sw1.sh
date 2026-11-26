echo "C300: ch_sw1"
S=/workspace/nox/web/site; cd $S; ls -l --time-style=+%H:%M sw.js nox-pwa.js; md5sum sw.js nox-pwa.js; echo ---sw; cat sw.js | cut -c1-700; echo ---pwa; cat nox-pwa.js | cut -c1-900
echo ---hdr; curl -sI -m5 localhost:8091/web/chat.html | head -12; curl -sI -m5 localhost:8091/web/sw.js | head -12; curl -sI -m5 localhost:8091/web/nox-chat-clean.js | head -12
