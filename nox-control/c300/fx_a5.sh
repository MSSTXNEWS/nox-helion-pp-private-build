S=/workspace/nox/web/site
echo ==pkgjson; grep -ln "package.json" $S/*.js $S/*.html 2>/dev/null | head; grep -o ".\{80\}package\.json.\{60\}" $S/nox-shell.js $S/nox-nav.js $S/nox-wow-bg.js $S/nox-glass.js 2>/dev/null | head -5
ls -d $S/vendor/three $S/vendor/postprocessing $S/vendor/motion $S/vendor/glasskit $S/vendor/driver.js $S/vendor/nox-planets 2>&1; ls $S/vendor/three $S/vendor/motion $S/vendor/glasskit $S/vendor/nox-planets 2>&1 | head -30
echo ==topbar; grep -n "className\|class=\"bar\|'bar'\|<header\|<nav" $S/nox-shell.js | head -12
echo ==supervisor; cat /etc/supervisor/conf.d/nox_web_chat_auth.conf | sed 's/\(KEY\|TOKEN\|PASS\)[A-Za-z_]*=[^ ,]*/\1=***/g' | head -20
grep -v "^#" /etc/supervisor/conf.d/caddy.conf | head -15
echo ==find; grep -rl "/api/status\|music/health" /workspace/nox --include=*.py --include=Caddyfile* --include=*.conf -s 2>/dev/null | head; ls /workspace/nox/web | head -30
ps -eo pid,args | grep -E "python|caddy|navidrome" | grep -v grep | cut -c1-200 | head -20
echo ==navi; curl -s -m5 http://127.0.0.1:4533/ping; curl -s -m5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4533/rest/ping.view; ls /workspace/nox/music_lib | head -5
echo ==pages404; for u in /web/vendor/three/package.json /api/status /music/health /memory/health /glm/v1/resume /glm/v1/nox/stats /web/vendor/nox-planets/nox-mars.jpg; do echo $u $(curl -s -m5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8091$u); done
