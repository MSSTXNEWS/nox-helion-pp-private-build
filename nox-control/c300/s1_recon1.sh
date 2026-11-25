S=/workspace/nox/web/site
cd $S; ls | head -300 | tr '\n' ' '; echo
echo ==CHAT; wc -c chat.html index.html nox-chat-*.css nox-chat-*.js nox-home-x.js nox_mode.js 2>&1
echo ==HTML; cat chat.html | cut -c1-400
