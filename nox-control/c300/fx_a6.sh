S=/workspace/nox/web/site
echo ==about-js; grep -n "package.json" $S/nox-p-about.js $S/nox-registry.js | cut -c1-400
ls /workspace/nox/web/pkg | head -30; ls /workspace/nox/web/pkg/* | head -40
echo ==grep; grep -rn "api/status\|/music\|/glm/\|/memory/" /workspace/nox/web/pkg --include=*.py -l | head
ps -eo pid,args | grep -E "8091|web_server|nox_web|navidrome" | grep -v grep | cut -c1-220
echo ==navi; curl -s -m5 -i http://127.0.0.1:4533/ping | head -8; curl -s -m5 -i http://127.0.0.1:4533/rest/ping.view | head -3; ls /workspace/nox/music_lib | head -3; ls /workspace/nox/ops | head -30
