S=/workspace/nox/web/site; cd $S
grep -n "\.stage\|\.feed\|\.dock\|\.col\b\|\.col{\|\.edge\|\.think\|\.hero\|\.composer\|#app\|\.msgs\|\.m\.a\|\.m\.u\|\.bubble\|\.ctb\|--dock\|--bar" nox-wow.css nox-unify.css nox-wow-fix.css nox-identity.css 2>/dev/null | cut -c1-330 | head -90
echo ==THINKJS; sed -n '157,160p' nox-wow.js | cut -c1-1200
ls wow 2>/dev/null | head; ls vendor/lottie-web/build | head -4
echo ==API; curl -s 127.0.0.1:8091/glm/v1/nox/stats | head -c 900; echo; curl -s 127.0.0.1:8091/api/chat/health | head -c 700
echo; grep -n "threads\b.*localStorage\|const LS\|LS_" nox-wow.js | head -8 | cut -c1-240
