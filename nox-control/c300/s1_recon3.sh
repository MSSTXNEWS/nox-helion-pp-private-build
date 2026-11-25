S=/workspace/nox/web/site
cd $S
echo ==SIZES; wc -c nox-wow.js nox-wow.css nox-unify.css nox-api.js nox-theme.js nox-nav*.js nox-pult.js vendor/nox-chat-ui/*.js vendor/nox-chat-ui/*.css 2>&1
echo ==FETCH-WOW; grep -on "fetch([^)]\{0,120\}" nox-wow.js nox-api.js nox-chat-x.js nox-pult.js nox-identity.js nox-notify.js | cut -c1-220
echo ==URLS; grep -on "['\"\`]\(\./\|\.\./\)\?\(api\|glm\|v1\|chat\|cal\|tts\|stt\|nox\)[a-zA-Z0-9_/.-]*" nox-wow.js | sort -u -t: -k3 | cut -c1-200 | head -80
echo ==UIFETCH; grep -o "fetch([^)]\{0,100\}" vendor/nox-chat-ui/chat-ui.js | sort | uniq -c | head -30
echo ==NOXAPI; head -c 3000 nox-api.js
echo ==BASE; grep -n "<base" chat.html index.html
echo ==ROUTES; grep -n "def do_GET\|def do_POST\|startswith\|path ==\|path in" /workspace/nox/web/pkg/server/web_server.py | cut -c1-200 | head -120
