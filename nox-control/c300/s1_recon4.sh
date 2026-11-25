S=/workspace/nox/web/site
cd $S
echo ==REL; grep -ons "['\"\`]\./\(glm\|api\|tts\|stt\|cal\|memory\|v7\|presence\|voice\|music\|brain\|drive\)[^'\"\`]*" *.js vendor/nox-chat-ui/chat-ui.js vendor/nox-chat-ui/*.js | cut -c1-160 | head -40
echo ==REL2; grep -ons "fetch([\`'\"][a-z][^'\"\`]*" *.js | head -20
echo ==API; grep -n "API *=" nox-identity.js | head -3; sed -n 235,250p nox-wow.js | cut -c1-300
echo ==FETCHCALLS; grep -ons "\(J\|call\|getJSON\|jget\|api\)([\`'\"][^'\"\`]*" nox-wow.js nox-pult.js nox-chat-x.js nox-nav*.js nox-ninja.js nox-home-x.js nox-dock*.js| head -30
echo ==WOWMSG; grep -n "className\s*=\s*'m \|class=\"m\|\.bubble\|acts\|think" nox-wow.js | cut -c1-260 | head -50
echo ==INDEX; cat index.html | cut -c1-500; echo; cat nox-home-x.js | cut -c1-400 | head -60
echo ==CHATPROXY; curl -s -o /dev/null -w "%{http_code} " localhost:8091/web/glm/v1/nox/stats localhost:8091/glm/v1/nox/stats localhost:8091/api/chat/health localhost:8091/web/api/chat/health localhost:8091/cal/events localhost:8091/web/cal/events; echo
grep -n "'/api/chat\|/api/chat\|v1/chat\|chat/completions\|/chat" nox-wow.js | cut -c1-240 | head
